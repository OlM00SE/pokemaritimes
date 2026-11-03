"""Map interactions on the engine model: people (object events), signs and hidden items (bg events).

Mirrors (pokeemerald-expansion 1.17.2):
  event_object_movement.c  GetCollisionAtCoords (an object is COLLISION_OBJECT_EVENT),
                           GetObjectEventIdByPosition / ObjectEventDoesElevationMatch
  field_control_avatar.c   GetInteractedObjectEventScript (the tile in front; across a counter),
                           GetInteractedBackgroundEventScript (bg elevation 0 or equal; a sign's
                           player_facing_dir), GetInFrontOfPlayerPosition (engine.event_elevation)
  trainer_see.c            GetTrainerApproachDistance{South,North,West,East} and
                           CheckPathBetweenTrainerAndPlayer: a trainer sees `range` tiles straight
                           ahead; every tile up to the player must be passable *for the trainer*
                           (collision, elevation against the trainer's own, other objects).

People block movement. Stationary people block their own tile; a wanderer may stand anywhere in
its movement range, so routes and walkers treat that whole box as blocked (conservative) while
the checker judges sealing on home tiles only. Objects with a hide flag are story props whose
presence depends on the story, so the checker doesn't judge them as blockers.
"""
import re
from .engine import World, DIRS, OPPOSITE

DIR_TOKEN = {"UP": "N", "DOWN": "S", "LEFT": "W", "RIGHT": "E"}
BG_FACING = {"BG_EVENT_PLAYER_FACING_NORTH": "N", "BG_EVENT_PLAYER_FACING_SOUTH": "S",
             "BG_EVENT_PLAYER_FACING_WEST": "W", "BG_EVENT_PLAYER_FACING_EAST": "E"}
TRAINER_TYPES = ("TRAINER_TYPE_NORMAL", "TRAINER_TYPE_SEE_ALL_DIRECTIONS", "TRAINER_TYPE_BURIED")
NO_SCRIPT = (None, "", "0", "0x0", "NULL")


def facings(movement_type):
    """Directions an object can face. FACE_/LOOK_/WALK_IN_PLACE_ types name theirs (FACE_DOWN,
    FACE_DOWN_AND_UP, ...); LOOK_AROUND, rotating and wandering types can face any way."""
    mt = (movement_type or "").replace("MOVEMENT_TYPE_", "")
    toks = [DIR_TOKEN[t] for t in re.findall(r"UP|DOWN|LEFT|RIGHT", mt)]
    if toks and re.match(r"(FACE|WALK_IN_PLACE|JOG_IN_PLACE|RUN_IN_PLACE|WALK_SLOWLY_IN_PLACE)_", mt):
        return set(toks)
    return set("NSWE")


def moves(o):
    """Whether the object walks about (wanders, walks a pattern, copies the player). Facing and
    in-place types never leave home, whatever their movement range says."""
    mt = (o.get("movement_type") or "").replace("MOVEMENT_TYPE_", "")
    return bool(re.search(r"WANDER|BACK_AND_FORTH|SEQUENCE|COPY_PLAYER|WALK_(UP|DOWN|LEFT|RIGHT)_AND", mt)) \
        and "IN_PLACE" not in mt


def wander_box(o, m):
    """Tiles an object on map m may stand on: its home, or its movement range for movers.
    IsCoordOutsideObjectEventMovementRange checks an axis only when its range isn't 0: a range of
    0 means no limit on that axis (the mover goes as far as the ground lets it), so the box spans
    the map there. Types that only move along one axis (WANDER_LEFT_AND_RIGHT, WALK_UP_AND_DOWN,
    ...) never leave their home row or column, which is why vanilla gives them a 0 on the other
    axis. Copy-player types (in grass) mirror the player and aren't modelled: home only."""
    if not moves(o):
        return {(o["x"], o["y"])}
    mt = o.get("movement_type") or ""
    if "COPY_PLAYER" in mt:
        return {(o["x"], o["y"])}
    W, H = m.layout.width, m.layout.height

    def span(home, r, size, fixed):
        if fixed:
            return [home]
        return list(range(size)) if r == 0 else list(range(max(0, home - r), min(size, home + r + 1)))
    rx, ry = int(o.get("movement_range_x", 0) or 0), int(o.get("movement_range_y", 0) or 0)
    horizontal_only = re.search(r"LEFT_AND_RIGHT|RIGHT_AND_LEFT", mt) is not None
    vertical_only = re.search(r"UP_AND_DOWN|DOWN_AND_UP", mt) is not None
    xs = span(o["x"], rx, W, vertical_only)
    ys = span(o["y"], ry, H, horizontal_only)
    return {(x, y) for x in xs for y in ys}


def object_elevation(m, o, xy=None):
    """The elevation an object has in the game while standing on xy (default: home). Every frame
    ObjectEventUpdateElevation sets it to the tile's elevation, except on multi-level (15)
    tiles, where the template's elevation stays. (Safari Zone's exit attendant has elevation 4
    in its template but stands on elevation 3 ground, and blocks like any elevation-3 person.)"""
    x, y = xy or (o["x"], o["y"])
    L = m.layout
    t = L.elev(x, y) if L.inb(x, y) else 15
    return int(o.get("elevation", 0)) if t == 15 else t


def hidden_by_flag(o):
    return str(o.get("flag", "0")) not in ("0", "", "None")


def is_item_ball(o):
    """An item ball: picked up once (its flag then hides it), so it isn't a permanent blocker."""
    return o.get("script") == "Common_EventScript_FindItem"


def is_trainer(o):
    return o.get("trainer_type", "TRAINER_TYPE_NONE") in TRAINER_TYPES


def sight_range(o):
    s = str(o.get("trainer_sight_or_berry_tree_id", "0"))
    return int(s) if s.isdigit() else 0


def label(kind, i, ev):
    """Short name for reports: the local id or script, else the index."""
    if kind == "object_events":
        name = ev.get("local_id") or ev.get("script") or ev.get("graphics_id", "")
        return f"object {i} ({str(name).replace('LOCALID_', '')})"
    what = ev.get("type", "bg")
    return f"{what} {i} ({ev.get('script') or ev.get('item') or ''})"


def obstacle_tiles(m, boxes=True, permanent_only=False):
    """{map tile: elevation} that people occupy (a person blocks a mover whose elevation is
    compatible: engine.World.step). boxes: a wanderer blocks its whole movement range (for
    planning walks); otherwise only its home tile. permanent_only: skip objects with a hide flag."""
    out = {}
    for o in m.events("object_events"):
        if permanent_only and hidden_by_flag(o):
            continue
        if o.get("trainer_type") == "TRAINER_TYPE_BURIED":
            continue                # Lavaridge Gym's trainers hidden in ash: not modelled as blockers
        for xy in (wander_box(o, m) if boxes else {(o["x"], o["y"])}):
            out[xy] = object_elevation(m, o, xy)
    return out


def world_with_people(p, m, boxes=True, extra=(), permanent_only=False):
    """World in which people block. The defaults are what a walker plans around in the game
    (anyone present, wanderers' whole range); route numbers use home tiles of the permanent
    people (boxes=False, permanent_only=True): a wanderer steps aside, an item ball is taken."""
    return World(p, m, {**obstacle_tiles(m, boxes, permanent_only), **{xy: 0 for xy in extra}})


def compatible(a, b):
    """AreElevationsCompatible; a is None when nobody is there."""
    return a is not None and (a == 0 or b == 0 or a == b)


def sight_lines(world, o, others):
    """{direction: [map tiles a trainer sees, nearest first]}: the tiles where a player standing
    there starts the battle. `others`: {tile: elevation} of the other people; one blocks the
    trainer's path where their elevations are compatible (equal, or either is 0)."""
    gx, gy = world.to_grid(o["x"], o["y"])
    elev = object_elevation(world.m, o)
    dirs = facings(o.get("movement_type")) if o.get("trainer_type") == "TRAINER_TYPE_NORMAL" else set("NSWE")
    cur_b = world.behavior(gx, gy)
    out = {}
    for d in sorted(dirs):
        dx, dy = DIRS[d]
        seen = []
        for k in range(1, sight_range(o) + 1):
            tx, ty = gx + dx * k, gy + dy * k
            # GetCollisionAtCoords for the trainer moving `d`: impassable tile, a directional
            # block (judged from the trainer's own tile), an elevation mismatch, or an object
            blocked = (world.cell(tx, ty) is None or world.collision(tx, ty) != 0
                       or cur_b in world.blocked[d] or world.behavior(tx, ty) in world.blocked[OPPOSITE[d]]
                       or world.elevation_mismatch(elev, tx, ty)
                       or compatible(others.get(world.to_map(tx, ty)), elev))
            if blocked:
                break
            seen.append(world.to_map(tx, ty))
        if seen:
            out[d] = seen
    return out


def interaction_spots(p, world, states, kind, ev):
    """Where the player can stand and press A to trigger `ev`: [(map x, y, facing)], from the
    given reachable player states (grid states, as World.explore returns)."""
    tx, ty = world.to_grid(ev["x"], ev["y"])
    counter = p.behavior_set("Counter")
    spots = set()
    for s in states:
        if not world.in_map(s[0], s[1]):
            continue
        for d, (dx, dy) in DIRS.items():
            fx, fy = s[0] + dx, s[1] + dy
            pos_elev = world.event_elevation(s, in_front=True)
            if kind == "object_events":
                hit = (fx, fy) == (tx, ty)
                # nobody there, but a counter in front: the engine looks one tile further
                if not hit and world.behavior(fx, fy) in counter and (fx + dx, fy + dy) == (tx, ty):
                    hit = True
                oe = object_elevation(world.m, ev)
                ok = hit and (oe == 0 or pos_elev == 0 or oe == pos_elev)
            else:
                be = int(ev.get("elevation", 0))
                need = BG_FACING.get(ev.get("player_facing_dir"))
                ok = (fx, fy) == (tx, ty) and (be == 0 or be == pos_elev) and (need is None or need == d)
            if ok:
                x, y = world.to_map(s[0], s[1])
                spots.add((x, y, d))
    return sorted(spots)


def sight_others(m, i):
    """The people who can stand in trainer i's way: the permanent ones, at home (as routes)."""
    o = m.events("object_events")[i]
    return {xy: e for xy, e in obstacle_tiles(m, boxes=False, permanent_only=True).items()
            if xy != (o["x"], o["y"])}


def analyse(p, m, starts, surf_starts=None, reach_free=None):
    """The map's people, signs and items on the engine model, from entrance states `starts`
    (on foot, grid states) and `surf_starts` (all entrances, for Surf). Returns a dict:
      reach_free:  foot states reachable when nobody blocks;
      reach:       foot states reachable with the permanent people standing where they stand;
      blockers:    map tiles of those people (home tiles);
      sight:       {object index: {dir: [tiles]}} for trainers;
      seen:        {object index: set of tiles in sight that the player can reach};
      spots:       {(kind, index): [(x, y, facing)]} where each event can be triggered on foot;
      surf_only:   set of (kind, index) that can only be triggered with Surf (swimmers...).
    reach_free: the free exploration, if the caller has it already (check_map does)."""
    blockers = obstacle_tiles(m, boxes=False, permanent_only=True)
    world = World(p, m, blockers)
    if reach_free is None:
        reach_free = World(p, m).explore(starts)
    reach = world.explore([s for s in starts if (s[0], s[1]) not in world.obstacles])
    surf = None
    on_map = {world.to_map(s[0], s[1]) for s in reach if world.in_map(s[0], s[1])}
    objs = m.events("object_events")
    out = {"reach_free": reach_free, "reach": reach, "blockers": blockers, "sight": {}, "seen": {},
           "spots": {}, "surf_only": set()}

    def spots_for(kind, i, ev):
        nonlocal surf
        got = interaction_spots(p, world, reach, kind, ev)
        if not got and surf_starts:
            if surf is None:
                surf = world.explore([s for s in surf_starts if (s[0], s[1]) not in world.obstacles],
                                     allow_surf=True)
            if interaction_spots(p, world, surf, kind, ev):
                out["surf_only"].add((kind, i))
        return got
    for i, o in enumerate(objs):
        if is_trainer(o):
            lines = sight_lines(world, o, sight_others(m, i))
            out["sight"][i] = lines
            out["seen"][i] = {t for ts in lines.values() for t in ts} & on_map
        if o.get("script") not in NO_SCRIPT:
            out["spots"][("object_events", i)] = spots_for("object_events", i, o)
    for i, b in enumerate(m.events("bg_events")):
        if b.get("type") in ("sign", "hidden_item"):
            out["spots"][("bg_events", i)] = spots_for("bg_events", i, b)
    return out


def wander_reach(m, o, others=()):
    """Tiles of a wanderer's range it can walk to from home, a step at a time as the engine moves
    it: open tiles (collision 0) whose elevation is compatible with the one it steps from
    (water, elevation 1, is never reached from land at 3), not through other people."""
    L, box = m.layout, wander_box(o, m)
    ok = lambda t: L.inb(*t) and L.coll(*t) == 0 and t not in others
    home = (o["x"], o["y"])
    seen, todo = {home}, [home]
    while todo:
        x, y = todo.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            t = (x + dx, y + dy)
            if t in box and t not in seen and ok(t):
                a, b = L.elev(x, y), L.elev(*t)
                if a == b or 0 in (a, b) or 15 in (a, b):
                    seen.add(t)
                    todo.append(t)
    return seen


def wanderer_seals(p, m, starts, exits, a):
    """[(exit label, object index, tile)]: exits a wanderer cuts off while it stands on that tile
    of its range (the other permanent people at home). Exits already cut off by the people at
    home are the sealing check's; only tiles it can walk to from home are tried (wander_reach)."""
    out = []
    L = m.layout
    reached = [(lbl, pred) for lbl, pred in exits if any(pred(s) for s in a["reach"])]
    for i, o in enumerate(m.events("object_events")):
        if not moves(o) or hidden_by_flag(o) or not reached:
            continue
        home = (o["x"], o["y"])
        others = {xy: e for xy, e in a["blockers"].items() if xy != home}
        for t in sorted(wander_reach(m, o, others) - {home}):
            w = World(p, m, {**others, t: object_elevation(m, o, t)})
            r = w.explore([s for s in starts if (s[0], s[1]) not in w.obstacles])
            out += [(lbl, i, t) for lbl, pred in reached if not any(pred(s) for s in r)]
    return out


def check_events(p, m, world, starts, surf_starts, exits, E, W, I, detail=None, reach_free=None):
    """Checker findings for people, signs and hidden items (see check_map).
    starts: foot entrance states; surf_starts: every entrance state (Surf); exits: [(label,
    predicate on a state)] for warps and connection edges, which must stay reachable with the
    people standing in the way; reach_free: check_map's foot exploration (nobody in the way).
    detail['events'] gets the analysis (events.analyse), so tools reuse the checker's entrances."""
    objs, bgs = m.events("object_events"), m.events("bg_events")
    if not objs and not any(b.get("type") in ("sign", "hidden_item") for b in bgs):
        return
    a = analyse(p, m, starts, surf_starts, reach_free)
    unreached = lambda key: not a["spots"].get(key) and key not in a["surf_only"]
    for kind, i in sorted(a["surf_only"]):
        ev = (objs if kind == "object_events" else bgs)[i]
        I("surf", f"{label(kind, i, ev)} at ({ev['x']},{ev['y']}) can only be reached with Surf")
    L = m.layout
    # people standing in the way: an exit reachable without them but not with them
    for lbl, pred in exits:
        if any(pred(s) for s in a["reach_free"]) and not any(pred(s) for s in a["reach"]):
            E("people", f"{lbl}: people standing at {sorted(a['blockers'])[:4]} cut it off")
    free_tiles = {world.to_map(s[0], s[1]) for s in a["reach_free"] if world.in_map(s[0], s[1])}
    tiles = {world.to_map(s[0], s[1]) for s in a["reach"] if world.in_map(s[0], s[1])}
    sealed = sorted(free_tiles - tiles - set(a["blockers"]))
    if sealed:
        W("people", f"{len(sealed)} tiles can only be reached by walking through people, e.g. {sealed[:6]}")
    # a wanderer may stop anywhere in its range and stand there a while. A WARN, not an ERROR: it
    # moves on (vanilla's house wanderers step in front of door mats: Fortree, Route 119...)
    seals = wanderer_seals(p, m, starts, exits, a)
    for i in sorted({i for _, i, _ in seals}):
        mine = [(lbl, t) for lbl, j, t in seals if j == i]
        W("people", f"{label('object_events', i, objs[i])} can wander onto {mine[0][1]} and cut off "
                    f"{mine[0][0]} until it moves on ({len(mine)} tile/exit pair{'s' if len(mine) > 1 else ''})")
    for i, o in enumerate(objs):
        name = label("object_events", i, o)
        if not L.inb(o["x"], o["y"]):
            continue
        if o.get("script") not in NO_SCRIPT and (not hidden_by_flag(o) or is_item_ball(o)) \
                and unreached(("object_events", i)):
            where = "stands on a solid tile and " if L.coll(o["x"], o["y"]) else ""
            W("people", f"{name} at ({o['x']},{o['y']}) {where}can't be talked to from anywhere a "
                        "walker reaches")
        if is_trainer(o):
            if sight_range(o) == 0 and o.get("trainer_type") == "TRAINER_TYPE_NORMAL":
                I("trainer", f"{name}: sight 0, battles only when talked to")
            elif not a["seen"].get(i):
                I("trainer", f"{name}: nobody can walk into its sight; battles only when talked to")
    for i, b in enumerate(bgs):
        if b.get("type") not in ("sign", "hidden_item") or not L.inb(b["x"], b["y"]):
            continue
        if unreached(("bg_events", i)):
            (W if b.get("type") == "sign" else I)(
                "sign" if b.get("type") == "sign" else "item",
                f"{label('bg_events', i, b)} at ({b['x']},{b['y']}) can't be read or found from anywhere "
                "a walker reaches (position, elevation or facing)")
    if detail is not None:
        detail["sight"], detail["spots"], detail["events"] = a["sight"], a["spots"], a
