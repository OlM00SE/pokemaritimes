"""Faithful model of overworld movement and event triggering.

Mirrors (pokeemerald-expansion 1.17.2):
  fieldmap.c            InitBackupMapLayoutData / Fill*Connection / GetMapBorderIdAt
  event_object_movement GetVanillaCollision, IsElevationMismatchAt, ObjectEventUpdateElevation,
                        IsMetatileDirectionallyImpassable, GetLedgeJumpDirection
  field_player_avatar   CheckForObjectEventCollision (ledge jump after collision, CanStopSurfing)
  field_control_avatar  warp/door/arrow/coord/bg event elevation matching

Not modelled (reported as 'unsupported' where encountered): sideways stairs,
rotating gates, acro/mach bike tiles, boulders, ice, currents, secret bases.
Coordinates in the public API are map coordinates; the padded grid is internal.
"""
from collections import deque
from .project import (MAP_OFFSET, ELEVATION_TRANSITION, ELEVATION_DEFAULT,
                      ELEVATION_MULTI_LEVEL, TILE_FLAG_SURFABLE, TILE_FLAG_HAS_ENCOUNTERS)
from .layout import pack

UNDEFINED = 0x3FF  # MAPGRID_UNDEFINED (metatile 0x3FF) marker
DIRS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_NAME = {"N": "UP", "S": "DOWN", "W": "LEFT", "E": "RIGHT"}
OPPOSITE = {"N": "S", "S": "N", "W": "E", "E": "W"}


class World:
    """The padded map grid the engine actually walks on, with neighbours' strips filled in."""

    def __init__(self, project, mapdata, obstacles=()):
        """obstacles: map tiles occupied by objects (people, item balls...), impassable like
        GetCollisionAtCoords' COLLISION_OBJECT_EVENT: {(x, y): object elevation}, or just tiles
        (elevation 0, which blocks everyone). Empty by default: the terrain checks judge the map
        without its people; mapkit/events.py decides which objects block."""
        self.p, self.m = project, mapdata
        if not isinstance(obstacles, dict):
            obstacles = {xy: 0 for xy in obstacles}
        self.obstacles = {self.to_grid(x, y): e for (x, y), e in obstacles.items()}
        L = mapdata.layout
        self.w, self.h = L.width, L.height
        self.W, self.H = self.w + MAP_OFFSET * 2 + 1, self.h + MAP_OFFSET * 2
        self.grid = [None] * (self.W * self.H)          # (block, tileset_pair) or None (undefined)
        self.conn_side = {}                                # grid cell -> (direction, neighbour map name)
        tp = L.tiles
        for y in range(self.h):
            for x in range(self.w):
                self.grid[(y + MAP_OFFSET) * self.W + x + MAP_OFFSET] = (L.get(x, y), tp)
        for c in mapdata.connections:
            name = project.const_to_map.get(c["map"])
            if name and c["direction"] in ("up", "down", "left", "right"):   # skip dive/emerge
                self._fill(c["direction"], c["offset"], project.load_map(name), name)
        B = project
        self.beh_jump = {B.mb("MB_JUMP_NORTH"): "N", B.mb("MB_JUMP_SOUTH"): "S",
                         B.mb("MB_JUMP_WEST"): "W", B.mb("MB_JUMP_EAST"): "E"}
        self.blocked = {d: set() for d in "NSWE"}          # MetatileBehavior_Is{North,..}Blocked
        for name, dirs in (("MB_IMPASSABLE_EAST", "E"), ("MB_IMPASSABLE_WEST", "W"),
                           ("MB_IMPASSABLE_NORTH", "N"), ("MB_IMPASSABLE_SOUTH", "S"),
                           ("MB_IMPASSABLE_NORTHEAST", "NE"), ("MB_IMPASSABLE_NORTHWEST", "NW"),
                           ("MB_IMPASSABLE_SOUTHEAST", "SE"), ("MB_IMPASSABLE_SOUTHWEST", "SW"),
                           ("MB_IMPASSABLE_WEST_AND_EAST", "WE"), ("MB_IMPASSABLE_SOUTH_AND_NORTH", "SN"),
                           ("MB_SECRET_BASE_BREAKABLE_DOOR", "WE")):
            if name in B.behaviors:
                for d in dirs:
                    self.blocked[d].add(B.mb(name))
        self.unsupported = {B.behaviors[n] for n in B.behaviors if
                            n.startswith("MB_SIDEWAYS_STAIRS") or "ICE" in n or "CURRENT" in n
                            or "ROTATING" in n or "MUDDY_SLOPE" in n}
        # field_player_avatar.c CheckAcroBikeCollision (sAcroBikeTrickMetatiles): entering these
        # yields a special collision in every player state; only the Acro Bike acts on it, so on
        # foot they are simply solid.
        self.acro_only = B.behavior_set("BumpySlope", "IsolatedVerticalRail", "IsolatedHorizontalRail",
                                        "VerticalRail", "HorizontalRail")

    def _fill(self, direction, offset, other, name):
        """Copy the neighbour's edge strip into the margin (fieldmap.c Fill*Connection)."""
        oL = other.layout
        tp = oL.tiles
        if direction in ("down", "up"):
            gy0 = self.h + MAP_OFFSET if direction == "down" else 0
            sy0 = 0 if direction == "down" else oL.height - MAP_OFFSET
            for dy in range(MAP_OFFSET):
                for sx in range(oL.width):
                    gx = offset + MAP_OFFSET + sx
                    sy = sy0 + dy
                    if 0 <= gx < self.W and 0 <= sy < oL.height:
                        self.grid[(gy0 + dy) * self.W + gx] = (oL.get(sx, sy), tp)
                        self.conn_side[(gx, gy0 + dy)] = (direction, name)
        else:
            gx0 = self.w + MAP_OFFSET if direction == "right" else 0
            sx0 = 0 if direction == "right" else oL.width - MAP_OFFSET
            cols = MAP_OFFSET + 1 if direction == "right" else MAP_OFFSET
            for dx in range(cols):
                for sy in range(oL.height):
                    gy = offset + MAP_OFFSET + sy
                    sx = sx0 + dx
                    if 0 <= gy < self.H and 0 <= sx < oL.width and gx0 + dx < self.W:
                        self.grid[gy * self.W + gx0 + dx] = (oL.get(sx, sy), tp)
                        self.conn_side[(gx0 + dx, gy)] = (direction, name)

    # ---- grid queries (grid coordinates) ----
    def cell(self, gx, gy):
        if 0 <= gx < self.W and 0 <= gy < self.H:
            return self.grid[gy * self.W + gx]
        return None

    def collision(self, gx, gy):
        c = self.cell(gx, gy)
        return 1 if c is None else (c[0] >> 10) & 3

    def elevation(self, gx, gy):
        c = self.cell(gx, gy)
        return 0 if c is None else c[0] >> 12

    def behavior(self, gx, gy):
        c = self.cell(gx, gy)
        return 0 if c is None else c[1].behavior(c[0] & 0x3FF)

    def flags(self, gx, gy):
        return self.p.tile_flags.get(self.behavior(gx, gy), 0)

    def in_map(self, gx, gy):
        return MAP_OFFSET <= gx < MAP_OFFSET + self.w and MAP_OFFSET <= gy < MAP_OFFSET + self.h

    @staticmethod
    def to_grid(x, y): return x + MAP_OFFSET, y + MAP_OFFSET
    @staticmethod
    def to_map(gx, gy): return gx - MAP_OFFSET, gy - MAP_OFFSET

    # ---- movement ----
    def elevation_mismatch(self, obj_elev, gx, gy):
        """event_object_movement.c IsElevationMismatchAt."""
        if obj_elev == ELEVATION_TRANSITION:
            return False
        e = self.elevation(gx, gy)
        if e in (ELEVATION_TRANSITION, ELEVATION_MULTI_LEVEL):
            return False
        return e != obj_elev

    def step(self, state, d):
        """One input in direction d from state (gx, gy, elev, prev_elev, surfing).
        elev = currentElevation (movement); prev_elev = previousElevation (event matching,
        field_player_avatar.c PlayerGetElevation). Returns (new_state, kind) with kind in
        walk|jump|surf_on|surf_off, or (None, reason)."""
        gx, gy, elev, prev, surfing = state
        dx, dy = DIRS[d]
        nx, ny = gx + dx, gy + dy
        cur_b, nb = self.behavior(gx, gy), self.behavior(nx, ny)
        # GetVanillaCollision: impassable if collision bits, undefined grid, or directional block.
        # IsMetatileDirectionallyImpassable (dir enum S=1,N=2,W=3,E=4):
        #   current tile: gOppositeDirectionBlockedMetatileFuncs = {IsSouth,IsNorth,IsWest,IsEast}Blocked
        #                 -> moving d out of a tile that is d-blocked fails
        #   target tile:  gDirectionBlockedMetatileFuncs = {IsNorth,IsSouth,IsEast,IsWest}Blocked
        #                 -> moving d into a tile blocked on its OPPOSITE(d) side fails
        impassable = (self.cell(nx, ny) is None or self.collision(nx, ny) != 0
                      or cur_b in self.blocked[d] or nb in self.blocked[OPPOSITE[d]])
        # an object in the way (COLLISION_OBJECT_EVENT), if the elevations are compatible
        # (AreElevationsCompatible: equal, or either is 0: a person on a bridge doesn't block the
        # path below); a ledge is still jumped (the jump test comes first in
        # CheckForObjectEventCollision), and surfing never lands on a person (CanStopSurfing)
        oe = self.obstacles.get((nx, ny))
        on_obj = oe is not None and (oe == 0 or elev == 0 or oe == elev)
        mismatch = (not impassable) and self.elevation_mismatch(elev, nx, ny)
        # CheckForObjectEventCollision: stop surfing, then ledge jump (regardless of collision)
        # CanStopSurfing: no object at elevation 3 there (GetObjectEventIdByPosition(x, y, 3))
        if mismatch and surfing and self.elevation(nx, ny) == ELEVATION_DEFAULT \
                and self.obstacles.get((nx, ny)) not in (ELEVATION_TRANSITION, ELEVATION_DEFAULT):
            return (nx, ny, ELEVATION_DEFAULT, ELEVATION_DEFAULT, False), "surf_off"
        if self.beh_jump.get(nb) == d:
            lx, ly = nx + dx, ny + dy
            return (lx, ly, *self._new_elev(elev, prev, nx, ny, lx, ly), surfing), "jump"
        if impassable:
            return None, "blocked"
        if on_obj:
            return None, "object"
        if mismatch:
            # On foot facing surfable water: Surf (TrySetupSurf needs a surfable tile in front).
            if not surfing and self.flags(nx, ny) & TILE_FLAG_SURFABLE:
                e = self.elevation(nx, ny)
                return (nx, ny, e, e, True), "surf_on"
            return None, "elevation"
        if nb in self.acro_only:
            return None, "acro_bike"
        if nb in self.unsupported:
            return None, "unsupported"
        return (nx, ny, *self._new_elev(elev, prev, gx, gy, nx, ny), surfing), "walk"

    def _new_elev(self, elev, prev, px, py, nx, ny):
        """ObjectEventUpdateElevation. Returns (currentElevation, previousElevation):
        no change if the new or old tile is multi-level (15); otherwise current = tile
        elevation, and previous follows it unless the tile is 0 (transition) or 15."""
        cur_t, old_t = self.elevation(nx, ny), self.elevation(px, py)
        if cur_t == ELEVATION_MULTI_LEVEL or old_t == ELEVATION_MULTI_LEVEL:
            return elev, prev
        return cur_t, (prev if cur_t == ELEVATION_TRANSITION else cur_t)

    def event_elevation(self, state, in_front=False):
        """Elevation used to match events: GetPlayerPosition uses previousElevation;
        GetInFrontOfPlayerPosition uses 0 when the player stands on a transition tile."""
        if in_front and self.elevation(state[0], state[1]) == ELEVATION_TRANSITION:
            return ELEVATION_TRANSITION
        return state[3]

    def arrival_state(self, gx, gy):
        """State after warping/connecting onto a tile (surfing if the tile is water)."""
        e = self.elevation(gx, gy)
        return (gx, gy, e, e if e not in (ELEVATION_TRANSITION, ELEVATION_MULTI_LEVEL) else ELEVATION_DEFAULT,
                bool(self.flags(gx, gy) & TILE_FLAG_SURFABLE))

    def explore(self, starts, allow_surf=False, limit=200000, edges=None):
        """BFS over states. Returns {state: (prev_state, dir, kind)}.
        edges: optional dict, filled with every transition taken: {state: [(next_state, dir, kind)]}."""
        seen = {s: None for s in starts}
        q = deque(starts)
        while q and len(seen) < limit:
            s = q.popleft()
            for d in "NSWE":
                ns, kind = self.step(s, d)
                if ns is None or (kind == "surf_on" and not allow_surf):
                    continue
                if edges is not None:
                    edges.setdefault(s, []).append((ns, d, kind))
                if ns in seen:
                    continue
                seen[ns] = (s, d, kind)
                if self.in_map(ns[0], ns[1]):     # stop at the map edge (we are now in a neighbour)
                    q.append(ns)
        return seen

    @staticmethod
    def surfing(state):
        return state[4]

    @staticmethod
    def path_to(seen, goal_state):
        out = []
        cur = goal_state
        while seen.get(cur):
            prev, d, kind = seen[cur]
            out.append((d, kind))
            cur = prev
        return out[::-1]
