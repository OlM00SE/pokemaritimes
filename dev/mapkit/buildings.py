"""Doors of building stamps: wire each placed door to the room the sketch names.

A sketch line `// stamp: mart @ 12,6 -> TownLab_Mart` says the Mart's door leads to the map
TownLab_Mart. On `mapgen --apply`:
  - if TownLab_Mart exists and a warp on this map already leads into it, that warp moves to
    the door. Its index doesn't change, so the room's exits (which point at it) stay right:
    a building moved in a redesign keeps its interior, its people and its warp ids;
  - if TownLab_Mart doesn't exist, it's created from the stamp's interior template
    (mapkit/interiors.py; a multi-floor template's ground floor is named <base>_1F), and a
    warp to it is appended;
  - a Pokémon Center also gets its heal location (the respawn point) moved or added, outside
    its door.
Refused (as problems): two doors naming one room, a room that exists without a warp here
leading into it, a name that doesn't fit the template's floors, two Pokémon Centers on one
map, and a warp that would end up inside a building.
A stamp with no `-> <Interior>` is left as a dead door (the checker warns).
"""
import re
from . import stamps, interiors
from .doors import map_const
from .transaction import edit

NAME = re.compile(r"[A-Z][A-Za-z0-9_]*")


class DoorPlan:
    def __init__(self):
        self.moves = []        # (warp index, (old x, y), (x, y), room)
        self.keeps = []        # (warp index, (x, y), room): already at the door
        self.creates = []      # (placement, interiors.Plan, door (x, y))
        self.heals = []        # (heal id or None, room (ground floor) name, (x, y)): None = a new one
        self.problems = []
        self.dead = []         # placements without a room
        self.created_warps = {}  # warp index -> room const, appended by preview() for new rooms

    def lines(self):
        out = []
        for i, old, new, room in self.moves:
            out.append(f"  door warp {i} -> {room}: moves {old} -> {new}")
        for i, xy, room in self.keeps:
            out.append(f"  door warp {i} -> {room}: at {xy}, unchanged")
        for pl, plan, door in self.creates:
            out.append(f"  door {door} -> {plan.first}: new room ({plan.kind}), a copy of {plan.template}"
                       + (f" with {len(plan.names) - 1} more floor(s)" if len(plan.names) > 1 else ""))
        for hid, room, xy in self.heals:
            out.append(f"  heal location {hid or '(new)'} for {room}: outside the door at {xy}")
        for pl in self.dead:
            out.append(f"  {pl.name} at ({pl.x},{pl.y}): no room named (-> <Interior>), the door stays dead")
        return out


def plan(p, m, placements):
    """The door plan for map m (its current map.json) with these stamp placements."""
    cat = stamps.catalog(p)
    dp = DoorPlan()
    warps = m.events("warp_events")
    rooms, owned, centers = {}, set(), []
    fp_all = {}
    for pl in placements:
        st = cat.get(pl.name)
        if st is None or st.door is None:
            continue                                   # compile names unknown or broken stamps
        for c in st.footprint(pl.x, pl.y):
            fp_all[c] = pl
        door = st.door_at(pl.x, pl.y)
        if st.kind == "pokemon_center":
            centers.append(pl)
        if not pl.interior:
            dp.dead.append(pl)
            continue
        if not NAME.fullmatch(pl.interior):
            dp.problems.append(f"{pl.name} at ({pl.x},{pl.y}): room name {pl.interior!r} must be a map name "
                               "(letters, digits, '_', starting with a capital)")
            continue
        if pl.interior in rooms:
            dp.problems.append(f"{pl.name} at ({pl.x},{pl.y}) and {rooms[pl.interior]} both lead to {pl.interior}")
            continue
        rooms[pl.interior] = f"{pl.name} at ({pl.x},{pl.y})"
        if pl.interior in p.map_names:
            const = interiors.load(p, pl.interior)["id"]
            hits = [i for i, w in enumerate(warps) if w["dest_map"] == const]
            if not hits:
                dp.problems.append(f"{pl.interior} exists, but no warp on {m.name} leads into it (it belongs to "
                                   "another door or map); name a new room, or wire it by hand")
                continue
            if len(hits) > 1:
                dp.problems.append(f"{len(hits)} warps on {m.name} lead into {pl.interior} (warps "
                                   f"{', '.join(map(str, hits))}): a stamp has one door, so it can't tell which "
                                   "to move; wire this building by hand")
                continue
            i = hits[0]
            owned.add(i)
            old = (warps[i]["x"], warps[i]["y"])
            (dp.keeps.append((i, door, pl.interior)) if old == door else dp.moves.append((i, old, door, pl.interior)))
            if st.kind == "pokemon_center":
                heal = next((e for e in interiors.heal_locations(p)["heal_locations"]
                             if e.get("respawn_map") == const and e["map"] == m.id), None)
                if heal and (heal["x"], heal["y"]) != (door[0], door[1] + 1):
                    dp.heals.append((heal["id"], pl.interior, (door[0], door[1] + 1)))
        else:
            base = interiors.base_for(p, st.interior, pl.interior) if st.interior in p.map_names else None
            if base is None:
                fl = interiors.floors(p, st.interior) if st.interior in p.map_names else []
                dp.problems.append(f"{pl.name} at ({pl.x},{pl.y}): a new room from {st.interior} has "
                                   f"{len(fl)} floors; name its ground floor <Base>_{fl[0].rsplit('_', 1)[-1]}"
                                   if len(fl) > 1 else f"{pl.name}: interior template {st.interior} is missing")
                continue
            try:
                ip = interiors.Plan(p, st.interior, base, st.kind)
            except interiors.InteriorError as ex:
                dp.problems.append(f"{pl.name} at ({pl.x},{pl.y}) -> {pl.interior}: {ex}")
                continue
            if st.kind == "pokemon_center":
                hid = interiors.heal_location_id(m.name)
                if any(e["id"] == hid for e in interiors.heal_locations(p)["heal_locations"]):
                    dp.problems.append(f"{hid} already exists: {m.name} has a Pokémon Center already "
                                       f"(a renamed Center room? keep its old name to keep its room)")
                    continue                    # neither the room nor the heal location is made
                dp.heals.append((None, ip.first, (door[0], door[1] + 1)))
            dp.creates.append((pl, ip, door))
    try:
        interiors.validate_new_names(p, [n for _, ip, _ in dp.creates for n in ip.names.values()])
    except interiors.InteriorError as ex:
        dp.problems.append(str(ex))
    if len(centers) > 1:
        dp.problems.append(f"{len(centers)} Pokémon Centers on {m.name}: one per map (its heal location is "
                           "named for the map)")
    new_xy = {i: new for i, _, new, _ in dp.moves}
    for i, w in enumerate(warps):
        xy = new_xy.get(i, (w["x"], w["y"]))
        pl = fp_all.get(xy)
        if pl and xy != cat[pl.name].door_at(pl.x, pl.y):
            dp.problems.append(f"warp {i} at {xy} (to {w['dest_map']}) would stand inside {pl.name} at "
                               f"({pl.x},{pl.y}); move or delete it in Porymap")
    return dp


def removed_doors(p, m, old_blocks, dp=None):
    """Problems for doors this build takes away while their warps (or a Center's heal location)
    stay: a building dropped from the sketch, or painted over. m holds the new blocks and the
    warps after preview(). Deleting a warp renumbers the ones after it (rooms find their door by
    index), so this is left to the designer: keep the building, or remove the warp (and its room)
    by hand and re-check the rooms that pointed past it."""
    door = p.behavior_set("WarpDoor")
    L = m.layout
    was_door = lambda x, y: L.inb(x, y) and L.tiles.behavior(old_blocks[y * L.width + x] & 0x3FF) in door
    is_door = lambda x, y: L.inb(x, y) and L.tiles.behavior(L.mid(x, y)) in door
    out = []
    for i, w in enumerate(m.events("warp_events")):
        if was_door(w["x"], w["y"]) and not is_door(w["x"], w["y"]):
            out.append(f"warp {i} (to {w['dest_map']}) stands on a door at ({w['x']},{w['y']}) that this build "
                       "removes; keep the building, or delete the warp and its room by hand")
    moving = {hid for hid, _, _ in dp.heals} if dp else set()
    for e in interiors.heal_locations(p)["heal_locations"]:
        if e["map"] == m.id and e["id"] not in moving and was_door(e["x"], e["y"] - 1) \
                and not is_door(e["x"], e["y"] - 1):
            out.append(f"{e['id']} is outside a door at ({e['x']},{e['y'] - 1}) that this build removes")
    return out


def preview(m, dp):
    """Apply the plan's warp changes to m's map.json in memory (for the checker): moves, and
    a warp for each room to be created (its map doesn't exist yet: dp.created_warps)."""
    warps = m.j.setdefault("warp_events", []) or []
    m.j["warp_events"] = warps
    for i, _, (x, y), _ in dp.moves:
        warps[i]["x"], warps[i]["y"] = x, y
    for pl, ip, (x, y) in dp.creates:
        dp.created_warps[len(warps)] = map_const(ip.first)
        warps.append({"x": x, "y": y, "elevation": 0, "dest_map": map_const(ip.first),
                      "dest_warp_id": str(ip.exit_id)})


def write_set(m, dp):
    files = [f"data/maps/{m.name}/map.json", interiors.HEAL_JSON]
    dirs = []
    for _, ip, _ in dp.creates:
        f, d = interiors.write_set(ip)
        files.extend(f)
        dirs.extend(d)
    return files, dirs


def apply(p, m, dp, tool="dev/mapgen.py"):
    """Write it: map.json (m.j after preview), the new rooms, the heal locations. Returns lines."""
    if dp.problems:
        raise interiors.InteriorError("invalid door plan: " + "; ".join(dp.problems))
    interiors.validate_new_names(p, [n for _, ip, _ in dp.creates for n in ip.names.values()])
    files, dirs = write_set(m, dp)
    with edit(p, files, dirs):
        return _apply(p, m, dp, tool)


def _apply(p, m, dp, tool):
    out = []
    warps = m.j["warp_events"]
    first_new = len(warps) - len(dp.creates)
    m.save()
    for k, (pl, ip, door) in enumerate(dp.creates):
        made = interiors.write(p, ip, m.name, m.id, first_new + k, tool=tool)
        out.append(f"  created {', '.join(made)} (door warp {first_new + k})")
    for hid, room, (x, y) in dp.heals:
        what = interiors.set_heal_location(p, hid or interiors.heal_location_id(m.name), m.id, x, y,
                                           map_const(room), interiors.nurse_local_id(room))
        out.append(f"  heal location {hid or interiors.heal_location_id(m.name)}: {what}")
    return out
