"""Place people, trainers, signs, items and hidden items on a map from a small spec file.

  python dev/events.py build design/maps/Route201_1.events.toml [--apply] [--force]
  python dev/events.py list <Map>

The spec (TOML, one per map) is the source of truth for the events it owns; everything else on
the map (events placed by hand in Porymap) is left alone. A build is a dry run unless --apply:
  - it checks each placement (in bounds, one event per tile, people on walkable ground, signs
    on a solid tile such as an `s` sign post from the sketch, names that exist in the game);
  - it runs the map checker on the unsaved result (mapkit/events.py: people cutting off an
    exit, people or signs nobody can reach, blind trainers) and refuses --apply on NEW errors;
  - it prints the route numbers before and after, including the trainers a crossing can't
    avoid, so "the route still plays the same" stays a number;
  - it writes dev/out/<Map>_events.png: the map with the events, the trainers' sight (red)
    and the tiles each event is triggered from (cyan).
--apply writes:
  - data/maps/<Map>/map.json: the owned events (removed and re-added; hand-placed ones keep
    their order and local ids, owned ones come after them);
  - data/maps/<Map>/scripts.pory: a marked block with the owned scripts (rebuilt each time). A map
    whose scripts.inc is still the empty stub that add_interior/new_map/Porymap make (no scripts
    at all) gets a scripts.pory started for it; any other map must be Poryscript already;
  - trainers: a TRAINER_ constant appended to include/constants/opponents.h (ids never move;
    the build prints how many are left) and the party in src/data/trainers.party;
  - item balls, hidden items and gifts: a flag appended to the Maritimes block in
    include/constants/flags.h, (MARITIMES_FLAGS_START + n); ids never move.
Run dev/fastbuild.py afterwards, then dev/tests/ingame_events.py <Map>.
dev/tests/id_budget.py checks the trainer ids, the flags and the save block.

Spec format (see design/maps/Route201_1.events.toml):
  map = "Route201_1"
  replaces = ["LittlerootTown_EventScript_BrendansHouseSign", ...]
                   hand-placed events (by script or local id) the spec takes over: removed, so a
                   spec event can stand on their tile (a placeholder cloned from vanilla)
  [[sign]]         name, at = [x, y], text            (sign post: draw `s` in the sketch there)
                   optional: facing = "up" (read only from below, like vanilla's Center signs)
  [[inspect]]      name, at, text                     something read on a solid tile: a poster, a
                   notice board, a shelf, a mailbox. Text is wrapped like dialogue (any length).
                   optional: facing (as a sign; wall things are read from below: "up")
  [[person]]       name, at, gfx, facing, text        (facing: down/up/left/right/around/wander)
                   optional: range = [rx, ry] for a wanderer, each 1-4 (default [1, 1]);
                   gift = "ITEM_...", count, after: gives the item once (text before, after
                   once given; a full bag gives nothing and asks again next time)
  [[trainer]]      name, at, gfx, facing, sight, class, trainer_name, party = ["Caterpie 3", ...],
                   intro, defeat, after               (optional: pic, gender, music)
  [[item]]         name, at, item                     (an item ball; picked up once)
  [[hidden_item]]  name, at, item                     (e.g. "ITEM_POTION")
Dialogue is wrapped to the message box by Poryscript's format(); a blank line in the spec starts
a new box. A sign keeps its own line breaks, as vanilla's route signs do.
"""
import argparse, copy, json, os, re, sys, tomllib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.layout import MapData
from mapkit.checks import check_map
from mapkit import events as ev, routes
from mapkit.render import render_layout

BEGIN = "// ---- dev/events.py: generated from {spec}. Edit the spec, not this block. ----"
END = "// ---- end of dev/events.py block ----"
OWNS = "// owns: "
FACING = {"down": "MOVEMENT_TYPE_FACE_DOWN", "up": "MOVEMENT_TYPE_FACE_UP",
          "left": "MOVEMENT_TYPE_FACE_LEFT", "right": "MOVEMENT_TYPE_FACE_RIGHT",
          "around": "MOVEMENT_TYPE_LOOK_AROUND", "wander": "MOVEMENT_TYPE_WANDER_AROUND"}
SIGN_FACING = {"any": "BG_EVENT_PLAYER_FACING_ANY", "up": "BG_EVENT_PLAYER_FACING_NORTH",
               "down": "BG_EVENT_PLAYER_FACING_SOUTH", "left": "BG_EVENT_PLAYER_FACING_WEST",
               "right": "BG_EVENT_PLAYER_FACING_EAST"}
KINDS = ("sign", "inspect", "person", "trainer", "item", "hidden_item")
FLAG_BLOCK = "MARITIMES_FLAGS_START"  # new flags: (MARITIMES_FLAGS_START + n), include/constants/flags.h
FLAG_BLOCK_END = "// ---- end of Maritimes flags ----"
WANDER_MAX = 4                        # a wander range beyond this leaves the camera view
TRAINER_NAME_LENGTH = 10
PARAGRAPH = "\\p"                     # a new message box


class SpecError(ValueError):
    pass


def caps(name):
    """'BugCatcher' -> 'BUG_CATCHER' (constant names)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).upper()


def map_token(m):
    return m.id[len("MAP_"):]


def local_id(tok, name):
    """LOCALID_<MAP>_<NAME>, the constant of a spec person, trainer or item ball."""
    return f"LOCALID_{tok}_{caps(name)}"


def gift_flag(tok, name):
    """FLAG_<MAP>_<NAME>_GIFT, set once a gift person has given their item."""
    return f"FLAG_{tok}_{caps(name)}_GIFT"


def pory_string(text):
    """A Poryscript string literal. The game's charmap has no straight double quote (vanilla
    writes “ ”), and Poryscript's format() can't take an escaped one, so a spec's "..." becomes
    “...”: opening at the start or after a space or bracket, closing otherwise."""
    text = re.sub(r'(^|(?<=[\s(\[]))"', "“", text)
    return '"' + text.replace('"', "”") + '"'


def fmt(text):
    """Dialogue: Poryscript's format() wraps it to the message box. In the spec, a blank line
    starts a new box (\\p); other line breaks are just spaces."""
    paras = [" ".join(q.split()) for q in re.split(r"\n\s*\n", text.strip())]
    return f"format({pory_string(PARAGRAPH.join(paras))})"


def sign_text(text):
    """A sign keeps its own lines, as vanilla's route signs do (ROUTE 201 / arrow, place)."""
    return pory_string("\\n".join(line.strip() for line in text.strip().split("\n")))


# ---------- reading the game's names ----------

def known_names(p):
    """Constants a spec may use: object graphics, items, species, trainer classes."""
    def enum(path, prefix):
        return set(re.findall(rf"\b({prefix}\w+)", open(p.path(path), encoding="utf-8").read()))
    party = open(p.path("src/data/trainers.party"), encoding="utf-8").read()
    classes = {}
    for block in party.split("=== ")[1:]:
        head = dict(re.findall(r"^(\w[\w ]*): (.+)$", block, re.M))
        if "Class" in head and head["Class"] not in classes:
            classes[head["Class"]] = head
    from mgba_bridge import species_ids
    return {"gfx": enum("include/constants/event_objects.h", "OBJ_EVENT_GFX_"),
            "items": enum("include/constants/items.h", "ITEM_"),
            "species": set(species_ids()), "classes": classes}


# ---------- the spec ----------

def load_spec(path, p, names):
    spec = tomllib.load(open(path, "rb"))
    if "map" not in spec:
        raise SpecError(f"{path}: needs map = \"<Map>\"")
    m = p.load_map(spec["map"])
    out, problems, seen = [], [], set()
    rp = spec.get("replaces", [])
    if not (isinstance(rp, list) and all(isinstance(r, str) for r in rp)):
        problems.append("replaces must be a list of script names or local ids")
    for kind in KINDS:
        for e in spec.get(kind, []):
            e = dict(e, kind=kind)
            nm = e.get("name", "")
            where = f"{kind} {nm or '?'}"
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", nm):
                problems.append(f"{where}: name must be CamelCase letters/digits (it names the script)")
            if nm in seen:
                problems.append(f"{where}: name used twice")
            seen.add(nm)
            at = e.get("at")
            if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, int) for v in at)):
                problems.append(f"{where}: at = [x, y] is required")
                continue
            e["x"], e["y"] = at
            need = {"sign": ["text"], "inspect": ["text"], "person": ["gfx", "text"], "hidden_item": ["item"],
                    "item": ["item"],
                    "trainer": ["gfx", "sight", "class", "trainer_name", "party", "intro", "defeat", "after"]}[kind]
            for k in need:
                if k not in e:
                    problems.append(f"{where}: {k} is required")
            if "gfx" in e:
                e["gfx"] = e["gfx"] if e["gfx"].startswith("OBJ_EVENT_GFX_") else "OBJ_EVENT_GFX_" + e["gfx"]
                if e["gfx"] not in names["gfx"]:
                    problems.append(f"{where}: unknown graphics {e['gfx']}")
            if kind in ("person", "trainer") and e.get("facing", "down") not in FACING:
                problems.append(f"{where}: facing must be one of {', '.join(FACING)}")
            if kind in ("hidden_item", "item") and e.get("item") not in names["items"]:
                problems.append(f"{where}: unknown item {e.get('item')}")
            if kind in ("sign", "inspect") and e.get("facing", "any") not in SIGN_FACING:
                problems.append(f"{where}: facing must be one of {', '.join(SIGN_FACING)}")
            if kind == "person":
                if e.get("facing") == "wander":
                    r = e.setdefault("range", [1, 1])
                    # the engine checks an axis only when its range isn't 0: a 0 lets them walk off
                    # along it as far as the ground goes (IsCoordOutsideObjectEventMovementRange)
                    if not (isinstance(r, list) and len(r) == 2 and all(isinstance(v, int) and 1 <= v <= WANDER_MAX for v in r)):
                        problems.append(f"{where}: range = [rx, ry], each 1-{WANDER_MAX} (the game reads 0 as no "
                                        "limit on that axis)")
                elif "range" in e:
                    problems.append(f"{where}: range is only for facing = \"wander\"")
                if "gift" in e:
                    if e.get("facing") == "wander":
                        problems.append(f"{where}: a gift person stands still (facing = \"wander\" with a gift "
                                        "isn't supported)")
                    if e["gift"] not in names["items"]:
                        problems.append(f"{where}: unknown gift item {e['gift']}")
                    if "after" not in e:
                        problems.append(f"{where}: a gift needs after = \"...\" (what they say once it's given)")
                    if not isinstance(e.get("count", 1), int) or not 1 <= e.get("count", 1) <= 99:
                        problems.append(f"{where}: count must be 1-99")
                elif "after" in e or "count" in e:
                    problems.append(f"{where}: after/count are only for a gift")
            if kind == "trainer":
                if e.get("class") not in names["classes"]:
                    problems.append(f"{where}: unknown trainer class {e.get('class')!r} (use one from "
                                    "src/data/trainers.party, e.g. 'Bug Catcher')")
                if len(e.get("trainer_name", "")) > TRAINER_NAME_LENGTH:
                    problems.append(f"{where}: trainer_name is longer than {TRAINER_NAME_LENGTH}")
                if not isinstance(e.get("sight"), int) or not 1 <= e.get("sight", 0) <= 8:
                    problems.append(f"{where}: sight must be 1-8 tiles")
                for mon in e.get("party", []):
                    mm = re.fullmatch(r"(.+?) (\d+)", mon)
                    sp = mm.group(1).upper().replace(" ", "_").replace(".", "").replace("'", "") if mm else None
                    if not mm or sp not in names["species"] or not 1 <= int(mm.group(2)) <= 100:
                        problems.append(f"{where}: party entry {mon!r} must be '<Species> <level>'")
                if not 1 <= len(e.get("party", [])) <= 6:
                    problems.append(f"{where}: a party has 1-6 Pokémon")
            out.append(e)
    if problems:
        raise SpecError("\n".join(f"  {s}" for s in problems))
    return m, out, list(rp)


# ---------- what the spec makes ----------

def generated(p, m, spec_events, spec_path):
    """(object_events, bg_events, pory block, trainers {const: party text}, hidden {flag: None},
    owned names) for the spec."""
    tok, L = map_token(m), m.layout
    objs, bgs, scripts, trainers, flags, owns = [], [], [], {}, [], []
    names = known_names(p)
    for e in spec_events:
        label = f"{m.name}_EventScript_{e['name']}"
        elev = L.elev(e["x"], e["y"]) if L.inb(e["x"], e["y"]) else 0
        if e["kind"] in ("sign", "inspect"):
            bgs.append({"type": "sign", "x": e["x"], "y": e["y"], "elevation": 0,
                        "player_facing_dir": SIGN_FACING[e.get("facing", "any")], "script": label})
            text = sign_text(e["text"]) if e["kind"] == "sign" else fmt(e["text"])
            scripts.append(f"script {label} {{\n    msgbox({text}, MSGBOX_SIGN)\n    end\n}}")
            owns.append(label)
        elif e["kind"] == "hidden_item":
            flag = f"FLAG_HIDDEN_ITEM_{tok}_{caps(e['name'])}"
            bgs.append({"type": "hidden_item", "x": e["x"], "y": e["y"], "elevation": elev,
                        "item": e["item"], "flag": flag})
            flags.append(flag)
            owns.append(flag)
        elif e["kind"] == "item":
            lid = local_id(tok, e["name"])
            flag = f"FLAG_ITEM_{tok}_{caps(e['name'])}"
            objs.append({"local_id": lid, "graphics_id": "OBJ_EVENT_GFX_ITEM_BALL", "x": e["x"], "y": e["y"],
                         "elevation": elev, "movement_type": "MOVEMENT_TYPE_FACE_DOWN",
                         "movement_range_x": 0, "movement_range_y": 0, "trainer_type": "TRAINER_TYPE_NONE",
                         "trainer_sight_or_berry_tree_id": e["item"], "script": "Common_EventScript_FindItem",
                         "flag": flag})
            flags.append(flag)
            owns += [lid, flag]
        else:
            lid = local_id(tok, e["name"])
            trainer = e["kind"] == "trainer"
            rx, ry = e.get("range", [0, 0]) if e.get("facing") == "wander" else (0, 0)
            objs.append({"local_id": lid, "graphics_id": e["gfx"], "x": e["x"], "y": e["y"],
                         "elevation": elev, "movement_type": FACING[e.get("facing", "down")],
                         "movement_range_x": rx, "movement_range_y": ry,
                         "trainer_type": "TRAINER_TYPE_NORMAL" if trainer else "TRAINER_TYPE_NONE",
                         "trainer_sight_or_berry_tree_id": str(e["sight"]) if trainer else "0",
                         "script": label, "flag": "0"})
            owns.append(lid)
            if trainer:
                const = f"TRAINER_{tok}_{caps(e['name'])}"
                owns.append(const)
                trainers[const] = party_text(const, e, names["classes"][e["class"]])
                scripts.append(f"script {label} {{\n    trainerbattle_single({const}, {fmt(e['intro'])}, "
                               f"{fmt(e['defeat'])})\n    msgbox({fmt(e['after'])}, MSGBOX_AUTOCLOSE)\n    end\n}}")
            elif "gift" in e:
                flag = gift_flag(tok, e["name"])
                flags.append(flag)
                owns.append(flag)
                scripts.append(gift_script(label, e, flag))
            else:
                scripts.append(f"script {label} {{\n    msgbox({fmt(e['text'])}, MSGBOX_NPC)\n    end\n}}")
    rel = os.path.relpath(spec_path, p.root).replace("\\", "/")
    block = "\n".join([BEGIN.format(spec=rel), OWNS + ", ".join(owns), ""] + [s + "\n" for s in scripts] + [END])
    return objs, bgs, block, trainers, flags, owns


def gift_script(label, e, flag):
    """A person who gives an item once. giveitem sets VAR_RESULT to FALSE when the bag is full;
    then, as in vanilla's gift scripts, goto Common_EventScript_ShowBagIsFull (it says so,
    releases and ends): the flag stays clear and they offer it again next time."""
    count = e.get("count", 1)
    return (f"script {label} {{\n"
            f"    lock\n    faceplayer\n"
            f"    if (flag({flag})) {{\n"
            f"        msgbox({fmt(e['after'])})\n"
            f"    }} else {{\n"
            f"        msgbox({fmt(e['text'])})\n"
            f"        giveitem({e['gift']}{f', {count}' if count != 1 else ''})\n"
            f"        if (var(VAR_RESULT) == FALSE) {{\n"
            f"            goto(Common_EventScript_ShowBagIsFull)\n"
            f"        }}\n"
            f"        setflag({flag})\n"
            f"        msgbox({fmt(e['after'])})\n"
            f"    }}\n"
            f"    release\n    end\n}}")


def party_text(const, e, like):
    """A trainers.party entry; Pic, Gender and Music follow the first vanilla trainer of the class."""
    lines = [f"=== {const} ===", f"Name: {e['trainer_name']}", f"Class: {e['class']}",
             f"Pic: {e.get('pic', like.get('Pic', e['class']))}",
             f"Gender: {e.get('gender', like.get('Gender', 'Male'))}",
             f"Music: {e.get('music', like.get('Music', 'Male'))}",
             "Double Battle: No", "AI: Check Bad Move", ""]
    for mon in e["party"]:
        sp, lvl = mon.rsplit(" ", 1)
        lines += [sp, f"Level: {lvl}", "IVs: 0 HP / 0 Atk / 0 Def / 0 SpA / 0 SpD / 0 Spe", ""]
    return "\n".join(lines)


def owned_names(pory_text):
    """Names the current generated block owns (empty if there is no block)."""
    for line in pory_text.splitlines():
        if line.startswith(OWNS):
            return {n.strip() for n in line[len(OWNS):].split(",") if n.strip()}
    return set()


def is_owned(kind, e, owns):
    if kind == "object_events":
        return e.get("local_id") in owns
    return e.get("script") in owns or e.get("flag") in owns


def is_replaced(kind, e, replaces):
    """A hand-placed event the spec takes over (removes): named by its script or local id."""
    return bool(replaces) and (e.get("script") in replaces or e.get("local_id") in replaces)


EMPTY_INC = re.compile(r"\A\s*(\w+)_MapScripts::\s*\.byte 0\s*\Z")


def pory_start(p, name):
    """The scripts.pory to start for a map whose scripts.inc is the empty stub (no scripts at
    all: a fresh add_interior/new_map room), else None. Poryscript then generates the same
    `<Map>_MapScripts:: .byte 0` plus the spec's block, so nothing else on the map changes."""
    inc = p.path("data/maps", name, "scripts.inc")
    mm = EMPTY_INC.match(open(inc, encoding="utf-8").read()) if os.path.exists(inc) else None
    if not mm or mm.group(1) != name:
        return None
    return (f"// {name}: map scripts in Poryscript. Started by dev/events.py when the map had no scripts;\n"
            f"// fastbuild generates scripts.inc from this file (never edit the .inc).\n\n"
            f"mapscripts {name}_MapScripts {{}}\n")


def with_block(pory_text, block):
    pat = re.compile(r"// ---- dev/events\.py: generated.*?" + re.escape(END), re.S)
    if pat.search(pory_text):
        return pat.sub(lambda _: block, pory_text)
    return pory_text.rstrip("\n") + "\n\n" + block + "\n"


# ---------- placement checks (beyond the map checker) ----------

def placement_problems(p, m, spec_events, owns, replaces=()):
    L, tp = m.layout, m.layout.tiles
    problems = []
    taken = {}
    for kind in ("object_events", "bg_events", "warp_events", "coord_events"):
        for e in m.events(kind):
            if not is_owned(kind, e, owns) and not (kind in ("object_events", "bg_events")
                                                    and is_replaced(kind, e, replaces)):
                taken[(e["x"], e["y"])] = f"a hand-placed {kind[:-7].replace('_', ' ')}"
    mine = {}
    for e in spec_events:
        xy, where = (e["x"], e["y"]), f"{e['kind']} {e['name']} at ({e['x']},{e['y']})"
        if not L.inb(*xy):
            problems.append(f"{where}: outside the map ({L.width}x{L.height})")
            continue
        if xy in taken or xy in mine:
            problems.append(f"{where}: the tile already has {taken.get(xy) or mine[xy]}")
        mine[xy] = f"{e['kind']} {e['name']}"
        solid = L.coll(*xy) != 0
        wet = p.tile_flags.get(tp.behavior(L.mid(*xy)), 0) & TILE_FLAG_SURFABLE
        if e["kind"] in ("person", "trainer", "item") and (solid or wet):
            problems.append(f"{where}: people stand on walkable ground, not on a "
                            f"{'water' if wet else 'solid'} tile")
        if e["kind"] == "sign" and not solid:
            problems.append(f"{where}: a sign needs a solid tile to stand on: draw `s` (sign post) "
                            "in the map's sketch here and rebuild the map first")
        if e["kind"] == "inspect" and not solid:
            problems.append(f"{where}: something to inspect stands on a solid tile (furniture, a wall, "
                            "a mailbox); this tile is walkable")
        if e["kind"] == "sign" and len(e["text"].strip().split("\n")) > 2:
            problems.append(f"{where}: a sign's message box shows two lines; vanilla's signs never "
                            "use more (a third would scroll)")
    return problems


# ---------- global ids: trainers and flags ----------

def plan_trainers(p, consts):
    """{const: id} for trainer constants that don't exist yet, appended after the last id."""
    txt = open(p.path("include/constants/opponents.h"), encoding="utf-8").read()
    have = set(re.findall(r"#define (TRAINER_\w+)\s+\d+", txt))
    count = int(re.search(r"#define TRAINERS_COUNT_EMERALD\s+(\d+)", txt).group(1))
    cap = int(re.search(r"#define MAX_TRAINERS_COUNT_EMERALD\s+(\d+)", txt).group(1))
    new = {c: count + i for i, c in enumerate(c for c in consts if c not in have)}
    if count + len(new) > cap:
        raise SpecError(f"  no room for {len(new)} new trainers: {count} of {cap} ids used (trainer "
                        "flags); reuse an unused vanilla trainer id or move the trainer flags")
    return new, cap - count - len(new)


def write_trainers(p, new, parties):
    path = p.path("include/constants/opponents.h")
    txt = open(path, encoding="utf-8").read()
    if new:
        last = list(re.finditer(r"^#define TRAINER_\w+\s+\d+[^\n]*\n", txt, re.M))[-1]
        add = "".join(f"#define {c:<35} {i}  // Maritimes: dev/events.py\n" for c, i in new.items())
        txt = txt[:last.end()] + add + txt[last.end():]
        txt = re.sub(r"(#define TRAINERS_COUNT_EMERALD\s+)(\d+)",
                     lambda mm: mm.group(1) + str(int(mm.group(2)) + len(new)), txt)
        open(path, "w", encoding="utf-8", newline="\n").write(txt)
    path = p.path("src/data/trainers.party")
    party = open(path, encoding="utf-8").read()
    for const, text in parties.items():
        pat = re.compile(rf"^=== {const} ===\n.*?(?=^=== |\Z)", re.S | re.M)
        if pat.search(party):
            party = pat.sub(lambda _: text + "\n", party)
        else:
            party = party.rstrip("\n") + "\n\n" + text + "\n"
    open(path, "w", encoding="utf-8", newline="\n").write(party)


def flag_block(p):
    """({flag: offset} already in the Maritimes block, its size) from include/constants/flags.h."""
    txt = open(p.path("include/constants/flags.h"), encoding="utf-8").read()
    have = {n: int(v, 0) for n, v in re.findall(rf"^#define (FLAG_\w+)\s+\({FLAG_BLOCK} \+ (0x[0-9A-Fa-f]+|\d+)\)", txt, re.M)}
    size = int(re.search(r"#define MARITIMES_FLAGS_COUNT\s+(\d+)", txt).group(1))
    return have, size


def plan_flags(p, flags):
    """{flag: offset in the Maritimes block} for flags that don't exist yet, after the last one.
    Flags that exist anywhere in flags.h (e.g. milestone 8's renamed unused flag) are kept."""
    txt = open(p.path("include/constants/flags.h"), encoding="utf-8").read()
    exists = set(re.findall(r"#define (FLAG_\w+)", txt))
    have, size = flag_block(p)
    nxt = max(have.values(), default=-1) + 1
    plan = {f: nxt + i for i, f in enumerate(f for f in flags if f not in exists)}
    if nxt + len(plan) > size:
        raise SpecError(f"  no room for {len(plan)} new flags: {nxt} of {size} in the Maritimes block used; "
                        "raise MARITIMES_FLAGS_COUNT in include/constants/flags.h (8 flags = 1 save byte; "
                        "dev/tests/id_budget.py shows the save block's room)")
    return plan, size - nxt - len(plan)


def write_flags(p, plan):
    if not plan:
        return
    path = p.path("include/constants/flags.h")
    txt = open(path, encoding="utf-8").read()
    add = "".join(f"#define {f:<43} ({FLAG_BLOCK} + 0x{o:X})  // Maritimes: dev/events.py\n" for f, o in plan.items())
    assert txt.count(FLAG_BLOCK_END) == 1, "flags.h: the Maritimes flag block marker is missing"
    txt = txt.replace(FLAG_BLOCK_END, add + FLAG_BLOCK_END)
    open(path, "w", encoding="utf-8", newline="\n").write(txt)


# ---------- commands ----------

def describe_event(kind, i, e, a):
    spots = a["spots"].get((kind, i), [])
    if kind == "object_events":
        what = "trainer" if ev.is_trainer(e) else "person"
        extra = f"{e['graphics_id'].replace('OBJ_EVENT_GFX_', '')}, {e['movement_type'].replace('MOVEMENT_TYPE_', '')}"
        if ev.is_trainer(e):
            seen = a["seen"].get(i, set())
            extra += f", sight {ev.sight_range(e)}: {len(seen)} reachable tiles"
    else:
        what = e.get("type")
        extra = e.get("item", "") if what == "hidden_item" else ""
    name = e.get("local_id") or e.get("script") or e.get("flag") or ""
    return (f"  {what:11} ({e['x']:>2},{e['y']:>2})  {name:42} {extra}"
            f"{'; ' if extra else ''}triggered from {len(spots)} tile/facing{'s' if len(spots) != 1 else ''}"
            + (" (Surf only)" if (kind, i) in a["surf_only"] else ""))


EMPTY = {"reach_free": {}, "reach": {}, "blockers": {}, "sight": {}, "seen": {}, "spots": {},
         "surf_only": set()}


def analyse_map(p, m):
    """(events.analyse result, checker detail, checker issues) from one checker run on m, so
    the entrances are exactly the checker's (door arrivals, Surf arrivals and all)."""
    detail = {}
    issues = check_map(p, m.name, None, None, mapdata=m, detail=detail)
    return detail.get("events", EMPTY), detail, issues


def cmd_list(p, name):
    m = p.load_map(name)
    pory = p.path("data/maps", name, "scripts.pory")
    owns = owned_names(open(pory, encoding="utf-8").read()) if os.path.exists(pory) else set()
    a, _, _ = analyse_map(p, m)
    owned = sum(is_owned(k, e, owns) for k in ("object_events", "bg_events") for e in m.events(k))
    print(f"{name}: {len(m.events('object_events'))} people, {len(m.events('bg_events'))} signs/items "
          f"({owned} owned by a spec; the rest placed by hand)")
    for kind in ("object_events", "bg_events"):
        for i, e in enumerate(m.events(kind)):
            print(describe_event(kind, i, e, a) + ("   [spec]" if is_owned(kind, e, owns) else ""))
    return 0


def cmd_build(p, spec_path, apply, force):
    names = known_names(p)
    try:
        m, spec_events, replaces = load_spec(spec_path, p, names)
    except SpecError as ex:
        print(f"{spec_path}: NOT BUILT, the spec has problems:\n{ex}")
        return 1
    pory_path = p.path("data/maps", m.name, "scripts.pory")
    started = None
    if not os.path.exists(pory_path):
        started = pory_start(p, m.name)
        if started is None:
            print(f"{m.name} has no scripts.pory (Poryscript) and its scripts.inc has scripts; this tool only "
                  "writes Poryscript, so convert the map's scripts to scripts.pory first")
            return 1
        print(f"  {m.name} has no scripts yet: --apply starts data/maps/{m.name}/scripts.pory")
    pory = started if started is not None else open(pory_path, encoding="utf-8").read()
    owns_before = owned_names(pory)
    replaced = [(k, e) for k in ("object_events", "bg_events") for e in m.events(k)
                if not is_owned(k, e, owns_before) and is_replaced(k, e, replaces)]
    for k, e in replaced:
        print(f"  replaces the hand-placed {'person' if k == 'object_events' else e.get('type')} at "
              f"({e['x']},{e['y']}): {e.get('local_id') or e.get('script')}")
    for r in replaces:
        if not any(r in (e.get("script"), e.get("local_id")) for _, e in replaced):
            print(f"  note: replaces {r}: no hand-placed event uses it (already replaced?)")
    problems = placement_problems(p, m, spec_events, owns_before, replaces)
    if problems:
        print(f"{m.name}: NOT BUILT, {len(problems)} placement problem(s):")
        print("\n".join(f"  {s}" for s in problems))
        return 1
    objs, bgs, block, parties, flags, owns = generated(p, m, spec_events, spec_path)

    # the map as it would be, in memory
    new = MapData(p, m.name)
    new.j = copy.deepcopy(m.j)
    for kind, mine in (("object_events", objs), ("bg_events", bgs)):
        new.j[kind] = [e for e in m.events(kind) if not is_owned(kind, e, owns_before)
                       and not is_replaced(kind, e, replaces)] + mine
    labels = {e["script"] for e in objs + bgs if "script" in e}
    p.script_labels.update(labels)            # the scripts exist once the block is written

    # what changes
    old_owned = {(k, json.dumps(e, sort_keys=True)) for k in ("object_events", "bg_events")
                 for e in m.events(k) if is_owned(k, e, owns_before)}
    new_owned = {(k, json.dumps(e, sort_keys=True)) for k, es in (("object_events", objs), ("bg_events", bgs)) for e in es}
    added, removed = new_owned - old_owned, old_owned - new_owned
    a, detail, issues = analyse_map(p, new)
    text_changed = with_block(pory, block) != pory
    print(f"{m.name}: {len(spec_events)} events from {os.path.relpath(spec_path, p.root)} "
          f"({len(added)} new or changed, {len(removed)} removed or changed, "
          f"{len(new_owned & old_owned)} unchanged; scripts and text "
          f"{'changed' if text_changed else 'unchanged'})")
    for kind in ("object_events", "bg_events"):
        for i, e in enumerate(new.events(kind)):
            mark = "" if is_owned(kind, e, set(owns)) else "   [hand-placed]"
            print(describe_event(kind, i, e, a) + mark)
    gone = owns_before - set(owns)
    for g in sorted(gone):
        if g.startswith(("TRAINER_", "FLAG_")):
            print(f"  note: {g} is no longer used by the spec; its id stays reserved (ids never move)")

    # global ids
    try:
        new_trainers, left = plan_trainers(p, list(parties))
        new_flags, flags_left = plan_flags(p, flags)
    except SpecError as ex:
        print(f"NOT BUILT:\n{ex}")
        return 1
    for c, i in new_trainers.items():
        print(f"  new trainer id {c} = {i} ({left} trainer slots left after this)")
    for f, o in new_flags.items():
        print(f"  new flag {f} = {FLAG_BLOCK} + 0x{o:X} ({flags_left} block flags left after this)")

    # the checker, before and after; route numbers, before and after
    before = {(c, msg) for s, c, msg in check_map(p, m.name, None, None, mapdata=m) if s == "ERROR"}
    new_errors = []
    for s, c, msg in issues:
        is_new = s == "ERROR" and (c, msg) not in before
        new_errors += [msg] if is_new else []
        if c in ("people", "sign", "item", "trainer", "surf", "script", "event") or s == "ERROR":
            print(f"  {s} {c}: {msg}{'   <- NEW' if is_new else ''}")
    if new.connections:
        print("routes (on foot, between edge connections; people block, trainers' sight counted):")
        for line in routes.describe(routes.route_stats(p, m), routes.route_stats(p, new)):
            print(line)
    out = p.path("dev", "out", f"{m.name}_events.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    render_layout(p, new.layout, 2, ("events", "grid"), new, detail).save(out)
    print(f"preview: dev/out/{m.name}_events.png (sight red, trigger tiles cyan)")
    print(f"checker: {sum(1 for s, _, _ in issues if s == 'ERROR')} errors ({len(new_errors)} new)")
    if not apply:
        print("dry run: nothing written (pass --apply)")
        return 1 if new_errors else 0
    if new_errors and not force:
        print("NOT APPLIED: fix the errors marked NEW first (or pass --force)")
        return 1
    new.save()
    with open(pory_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(with_block(pory, block))
    write_trainers(p, new_trainers, parties)
    write_flags(p, new_flags)
    print(f"applied: data/maps/{m.name}/map.json, scripts.pory"
          + (", opponents.h, trainers.party" if parties else "") + (", flags.h" if new_flags else "")
          + "\nnext: dev/fastbuild.py, then dev/tests/ingame_events.py " + m.name)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["build", "list"])
    ap.add_argument("target", help="a spec file (build) or a map name (list)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="apply even with new checker errors")
    a = ap.parse_args()
    p = Project()
    if a.cmd == "list":
        return cmd_list(p, a.target)
    return cmd_build(p, a.target, a.apply, a.force)


if __name__ == "__main__":
    sys.exit(main())
