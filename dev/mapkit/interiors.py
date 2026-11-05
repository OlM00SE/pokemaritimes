"""Interiors: a copy of a vanilla interior (every floor) behind a new door, made to work.

Used by dev/add_interior.py (a door on a hand-painted map) and mapkit/buildings.py (the doors
of building stamps). The copy keeps the vanilla layout (no new map.bin): the floors become new
maps in gMapGroup_IndoorMaritimes, their warps are rewired to the new door and to each other,
and vanilla's story events are stripped. What a kind of building needs is added back:
  plain           nothing (dev/events.py adds people and signs later)
  pokemon_center  the ground floor's nurse heals and is the whiteout respawn NPC; entering sets
                  the respawn point (a heal location in src/data/heal_locations.json, outside
                  the door); upstairs keeps vanilla's cable club (its attendants and map scripts
                  are shared scripts, the same in every Center)
  mart            the clerk sells MART_STOCK
Warps to shared rooms (the Union Room, the Trade Center: rooms whose every exit is
MAP_DYNAMIC, i.e. "back where you came from") are kept as they are. Any other warp must lead
to the vanilla exterior or to another copied floor, or the copy is refused.
"""
import json, os, re
from .doors import map_const
from .mapjson import dump_json, add_to_group, add_script_includes, indoor_closure, shared_room

GROUP = "gMapGroup_IndoorMaritimes"
STRIP_KEYS = ("shared_events_map", "shared_scripts_map")
KINDS = ("plain", "pokemon_center", "mart")
MART_STOCK = ["ITEM_POKE_BALL", "ITEM_POTION", "ITEM_ANTIDOTE", "ITEM_PARALYZE_HEAL", "ITEM_AWAKENING"]
NURSE_GFX = "OBJ_EVENT_GFX_NURSE"
CLERK_GFX = "OBJ_EVENT_GFX_MART_EMPLOYEE"
HEAL_JSON = "src/data/heal_locations.json"
BEGIN = "// ---- {tool}: the {kind}'s workings. Edit freely; the tool writes this block once. ----"


class InteriorError(ValueError):
    pass


def load(p, name):
    return json.load(open(p.path("data/maps", name, "map.json"), encoding="utf-8"))


def is_indoor(p, name):
    return load(p, name).get("map_type") == "MAP_TYPE_INDOOR"


def floors(p, first):
    """`first` plus the vanilla indoor maps reachable from it without going outside, skipping
    shared rooms (mapjson.indoor_closure). Breadth-first."""
    return [first] + indoor_closure(p, [first])


def exterior_of(p, template):
    """The vanilla outdoor map the template's ground floor leads out to (its map const)."""
    outs = [w["dest_map"] for w in load(p, template).get("warp_events") or []
            if p.const_to_map.get(w["dest_map"]) and not is_indoor(p, p.const_to_map[w["dest_map"]])]
    if not outs:
        raise InteriorError(f"{template}: none of its warps leads outdoors, so there is no exit to rewire")
    return outs[0]


def floor_names(p, template, base):
    """{vanilla floor: new map name}: `base` for a one-room interior, else base + each floor's
    suffix (HomeTown_House2 -> HomeTown_House2_1F, _2F)."""
    fl = floors(p, template)
    if len(fl) == 1:
        return {fl[0]: base}
    names = {v: f"{base}_{v.rsplit('_', 1)[-1]}" for v in fl}
    if len(set(names.values())) != len(fl):
        names = {v: f"{base}_{i + 1}" for i, v in enumerate(fl)}
    return names


def base_for(p, template, first_floor):
    """The base name whose ground floor is `first_floor` (inverse of floor_names), or None if
    no base gives that name (e.g. a two-floor template named without its _1F suffix)."""
    fl = floors(p, template)
    if len(fl) == 1:
        return first_floor
    suffix = "_" + fl[0].rsplit("_", 1)[-1]
    if first_floor.endswith(suffix) and floor_names(p, template, first_floor[:-len(suffix)])[fl[0]] == first_floor:
        return first_floor[:-len(suffix)]
    return None


class Plan:
    """What a copy will make: template, kind, the vanilla exterior, {vanilla floor: new name}."""

    def __init__(self, p, template, base, kind="plain"):
        if template not in p.map_names:
            raise InteriorError(f"no such map {template}")
        if kind not in KINDS:
            raise InteriorError(f"kind {kind!r} is not one of {KINDS}")
        self.template, self.kind, self.base = template, kind, base
        self.exterior = exterior_of(p, template)
        self.names = floor_names(p, template, base)
        self.first = self.names[template]
        for n in self.names.values():
            if n in p.map_names:
                raise InteriorError(f"map {n} already exists")
            if map_const(n) in p.const_to_map:
                raise InteriorError(f"{n} would get id {map_const(n)}, which {p.const_to_map[map_const(n)]} uses")
        vconsts = {load(p, v)["id"] for v in self.names}
        for v in self.names:
            for w in load(p, v).get("warp_events") or []:
                d = w["dest_map"]
                dn = p.const_to_map.get(d)
                if d != self.exterior and d not in vconsts and not (dn and shared_room(p, dn)):
                    raise InteriorError(f"{v} has a warp at ({w['x']},{w['y']}) to {d}, which can't be rewired "
                                        "(a second exit?); clone this building by hand in Porymap")
        if kind == "pokemon_center" and not any(o["graphics_id"] == NURSE_GFX for o in load(p, template)["object_events"]):
            raise InteriorError(f"{template} has no nurse to copy (kind pokemon_center)")
        if kind == "mart" and not any(o["graphics_id"] == CLERK_GFX for o in load(p, template)["object_events"]):
            raise InteriorError(f"{template} has no clerk to copy (kind mart)")
        self.exit_id = self.exit_warp_id(p)

    def exit_warp_id(self, p):
        """Index of the ground floor's first warp leading outside: the new door's warp points at it."""
        return next(i for i, w in enumerate(load(p, self.template)["warp_events"]) if w["dest_map"] == self.exterior)

    def describe(self, p):
        return [f"{v}  ->  {n}  ({map_const(n)}, layout {load(p, v)['layout']})" for v, n in self.names.items()]


def token(name):
    return map_const(name)[len("MAP_"):]


def heal_location_id(outdoor_name):
    return f"HEAL_LOCATION_{token(outdoor_name)}"


def nurse_local_id(first_floor):
    return f"LOCALID_{token(first_floor)}_NURSE"


def map_script_refs(p, vanilla):
    """The vanilla floor's map scripts that point at shared labels (not its own), e.g.
    MAP_SCRIPT_ON_RESUME -> CableClub_OnResume: kept, because they work the same anywhere."""
    inc = p.path("data/maps", vanilla, "scripts.inc")
    if not os.path.exists(inc):
        return []
    txt = open(inc, encoding="utf-8").read()
    return [(t, lab) for t, lab in re.findall(r"map_script\s+(MAP_SCRIPT_\w+)\s*,\s*(\w+)", txt)
            if not lab.startswith(vanilla)]


def shared_object(vanilla, o):
    """An object whose script is shared (Common_/CableClub_...), with no flag of its own."""
    return not o["script"].startswith(vanilla) and str(o.get("flag", "0")) == "0" and o["script"] != "0x0"


def write(p, plan, outdoor_name, outdoor_id, ext_warp_id, tool="dev/add_interior.py"):
    """Write the copied floors. Their exits lead to warp `ext_warp_id` of `outdoor_name`
    (`outdoor_id` its map const), which the caller creates or moves. Registers the maps in
    the indoor group and data/event_scripts.s. Returns the new map names."""
    vconst = {load(p, v)["id"]: n for v, n in plan.names.items()}
    ext = load(p, outdoor_name)
    for v, n in plan.names.items():
        j = load(p, v)
        j["id"], j["name"] = map_const(n), n
        if plan.kind == "plain":                 # a house plays the town's music; a Center or
            j["music"] = ext.get("music", j["music"])  # a Mart keeps its own (MUS_POKE_CENTER/MART)
        j["region_map_section"] = ext.get("region_map_section", j["region_map_section"])
        if "region" in j and "region" not in ext:
            del j["region"]
        for k in STRIP_KEYS:
            j.pop(k, None)
        objs = j.get("object_events") or []
        first = v == plan.template
        keep = []
        if plan.kind == "pokemon_center" and first:
            nurse = next(o for o in objs if o["graphics_id"] == NURSE_GFX)
            keep = [dict(nurse, local_id=nurse_local_id(n), script=f"{n}_EventScript_Nurse")]
        elif plan.kind == "pokemon_center":
            keep = [o for o in objs if shared_object(v, o)]           # the cable club
        elif plan.kind == "mart" and first:
            clerk = next(o for o in objs if o["graphics_id"] == CLERK_GFX)
            keep = [dict(clerk, script=f"{n}_EventScript_Clerk")]
            keep[0].pop("local_id", None)
        for o in keep:
            if "local_id" in o and not o["local_id"].startswith(f"LOCALID_{token(n)}"):
                del o["local_id"]                                      # vanilla's id names a vanilla map
        j["object_events"], j["coord_events"], j["bg_events"] = keep, [], []
        for w in j.get("warp_events") or []:
            if w["dest_map"] == plan.exterior:
                w["dest_map"], w["dest_warp_id"] = outdoor_id, str(ext_warp_id)
            elif w["dest_map"] in vconst:
                w["dest_map"] = map_const(vconst[w["dest_map"]])
        folder = p.path("data/maps", n)
        os.makedirs(folder, exist_ok=True)
        dump_json(os.path.join(folder, "map.json"), j)
        pory = scripts_for(p, plan, v, n, outdoor_name, tool)
        if pory is None:
            with open(os.path.join(folder, "scripts.inc"), "w", encoding="utf-8", newline="\n") as f:
                f.write(f"{n}_MapScripts::\n\t.byte 0\n")
        else:
            with open(os.path.join(folder, "scripts.pory"), "w", encoding="utf-8", newline="\n") as f:
                f.write(pory)
    add_to_group(p, GROUP, list(plan.names.values()))
    add_script_includes(p, list(plan.names.values()))
    for attr in ("map_names", "const_to_map", "script_labels"):     # the project now has new maps
        p.__dict__.pop(attr, None)
    return list(plan.names.values())


def scripts_for(p, plan, vanilla, name, outdoor_name, tool):
    """The scripts.pory a floor of this kind needs, or None for the empty stub (plain rooms)."""
    refs = map_script_refs(p, vanilla) if plan.kind == "pokemon_center" else []
    first = vanilla == plan.template
    body, mapscripts = [], [f"    {t}: {lab}" for t, lab in refs]
    if plan.kind == "pokemon_center" and first:
        mapscripts.insert(0, f"    MAP_SCRIPT_ON_TRANSITION {{\n        setrespawn({heal_location_id(outdoor_name)})\n    }}")
        body.append(f"script {name}_EventScript_Nurse {{\n"
                    f"    setvar(VAR_0x800B, {nurse_local_id(name)})\n"
                    f"    call(Common_EventScript_PkmnCenterNurse)\n"
                    f"    waitmessage\n    waitbuttonpress\n    release\n    end\n}}")
    elif plan.kind == "mart" and first:
        body.append(f"script {name}_EventScript_Clerk {{\n"
                    f"    lock\n    faceplayer\n"
                    f"    message(gText_HowMayIServeYou)\n    waitmessage\n"
                    f"    pokemart({name}_Stock)\n"
                    f"    msgbox(gText_PleaseComeAgain, MSGBOX_DEFAULT)\n"
                    f"    release\n    end\n}}")
        body.append(f"mart {name}_Stock {{\n" + "".join(f"    {i}\n" for i in MART_STOCK) + "}")
    if not mapscripts and not body:
        return None
    head = (f"// {name}: copied from {vanilla} by {tool} ({plan.kind}).\n"
            f"// fastbuild generates scripts.inc from this file (never edit the .inc).\n\n")
    ms = f"mapscripts {name}_MapScripts {{\n" + "\n".join(mapscripts) + ("\n" if mapscripts else "") + "}\n"
    return head + ms + ("\n" + BEGIN.format(tool=tool, kind=plan.kind.replace("_", " ")) + "\n"
                        + "\n\n".join(body) + "\n" if body else "")


# ---------- heal locations ----------

def heal_locations(p):
    return json.load(open(p.path(HEAL_JSON), encoding="utf-8"))


def set_heal_location(p, hid, outdoor_const, x, y, respawn_map=None, npc=None):
    """Move heal location `hid` to (x, y) on `outdoor_const` (nothing else about it changes), or
    add it, appended so no id moves, with the room and NPC a whiteout respawns at. Returns
    "added", "moved" or "unchanged". A save made at the old spot no longer matches a moved one:
    its whiteout then respawns outside, at the old spot."""
    data = heal_locations(p)
    for e in data["heal_locations"]:
        if e["id"] == hid:
            if (e["map"], e["x"], e["y"]) == (outdoor_const, x, y):
                return "unchanged"
            e["map"], e["x"], e["y"] = outdoor_const, x, y
            dump_json(p.path(HEAL_JSON), data)
            return "moved"
    if not (respawn_map and npc):
        raise InteriorError(f"{hid} doesn't exist; adding it needs the respawn room and NPC")
    data["heal_locations"].append({"id": hid, "map": outdoor_const, "x": x, "y": y,
                                   "respawn_map": respawn_map, "respawn_npc": npc})
    dump_json(p.path(HEAL_JSON), data)
    return "added"
