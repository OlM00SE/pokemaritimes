"""Python client for bridge.lua: launch mGBA, drive input, screenshot, read RAM.

    from mgba_bridge import Emu
    with Emu(rom) as e:
        e.press("A", 5); e.wait(60); e.shot("x.png"); print(e.location())
"""
import os, re, socket, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# mGBA dev build lives outside the repo: RomHackDev/tools/mgba/mgba-dev (stable 0.10.x lacks --script)
MGBA = os.environ.get("MGBA_EXE") or os.path.normpath(
    os.path.join(REPO, "..", "..", "tools", "mgba", "mgba-dev", "mGBA.exe"))
BRIDGE = os.path.join(HERE, "bridge.lua")
PORT = 8765
UNTHROTTLED = ["-C", "videoSync=0", "-C", "audioSync=0"]


def config_flag(config_rel, define, repo=REPO):
    """Resolve a config define like WE_FLAG_NO_ENCOUNTER -> FLAG_UNUSED_0x021 -> 0x21 (0 if unset)."""
    txt = open(os.path.join(repo, config_rel), encoding="utf-8").read()
    m = re.search(rf"#define\s+{define}\s+(\w+)", txt)
    if not m or m.group(1) == "0":
        return 0
    flags = open(os.path.join(repo, "include", "constants", "flags.h"), encoding="utf-8").read()
    f = re.search(rf"#define\s+{m.group(1)}\s+(0x[0-9A-Fa-f]+|\d+)", flags)
    return int(f.group(1), 0) if f else 0


def enum_ids(header, prefix, repo=REPO, _cache={}):
    """{'NAME': value} for the explicitly numbered PREFIX_NAME = n entries of a constants header,
    e.g. enum_ids('species.h', 'SPECIES') (cached per header)."""
    key = (repo, header, prefix)
    if key not in _cache:
        src = open(os.path.join(repo, "include", "constants", header), encoding="utf-8").read()
        _cache[key] = {k: int(v) for k, v in re.findall(rf"\b{prefix}_(\w+)\s*=\s*(\d+)", src)}
    return _cache[key]


def species_ids(repo=REPO):
    """{'BIDOOF': 399, ...} from the SPECIES_* enum in include/constants/species.h."""
    return enum_ids("species.h", "SPECIES", repo)


def move_ids(repo=REPO):
    """{'SURF': 57, ...} from the MOVE_* enum in include/constants/moves.h."""
    return enum_ids("moves.h", "MOVE", repo)


def flag_id(name, repo=REPO, _cache={}):
    """Value of a flag constant, evaluating flags.h expressions like (SYSTEM_FLAGS + 0x0).
    Where a header defines a name twice under #if (Emerald vs FRLG), the Emerald one wins.
    Cross-checked against the '// FLAG_0x...' comment flags.h keeps next to most flags."""
    if not _cache:
        notes = {}
        for h in ("flags.h", "opponents.h"):
            txt = open(os.path.join(repo, "include", "constants", h), encoding="utf-8").read()
            for n, expr, note in re.findall(r"^#define\s+(\w+)\s+([^\n/]+)(//[^\n]*)?", txt, re.M):
                expr = expr.strip()
                if n in _cache and "FRLG" in expr:
                    continue
                _cache[n] = expr
                m = re.search(r"FLAG_(0x[0-9A-Fa-f]+)", note or "")
                if m:
                    notes[n] = int(m.group(1), 0)
        _cache["__notes__"] = notes

    def ev(n, depth=0):
        expr = _cache[n]
        if depth > 20:
            raise ValueError(f"flag {n}: define chain too deep")
        expr = re.sub(r"\b([A-Z_][A-Z0-9_]*)\b", lambda m: str(ev(m.group(1), depth + 1)), expr)
        if not re.fullmatch(r"[\s()+\-*0-9xXa-fA-F]+", expr):
            raise ValueError(f"flag {n}: cannot evaluate {expr!r}")
        return int(eval(expr, {"__builtins__": {}}))
    v = ev(name)
    note = _cache["__notes__"].get(name)
    if note is not None and note != v:
        raise ValueError(f"{name}: evaluated {v:#x} but flags.h says {note:#x}")
    return v


def load_map_names(repo=REPO):
    """{(group, num): 'MapName'} from the generated include/constants/map_groups.h."""
    names = {}
    path = os.path.join(repo, "include", "constants", "map_groups.h")
    if os.path.exists(path):
        # pret: "#define MAP_X (n | (g << 8))"   expansion: "MAP_X = (n | (g << 8)),"
        pat = re.compile(r"MAP_(\w+)\s*=?\s*\((\d+) \| \((\d+) << 8\)\)")
        for line in open(path):
            m = pat.search(line)
            if m:
                names[(int(m.group(3)), int(m.group(2)))] = m.group(1)
    return names


def load_symbols(map_path):
    """Parse a GNU ld .map file into {symbol: address}."""
    syms = {}
    pat = re.compile(r"^\s+0x([0-9a-fA-F]{8})\s+(\w+)(?:\s*=\s*\.)?\s*$")
    with open(map_path, errors="replace") as f:
        for line in f:
            m = pat.match(line)
            if m:
                syms.setdefault(m.group(2), int(m.group(1), 16))
    return syms


class Emu:
    def __init__(self, rom, extra_args=(), boot_timeout=20):
        self.rom = os.path.abspath(rom)
        mp = os.path.splitext(self.rom)[0] + ".map"
        self.sym = load_symbols(mp) if os.path.exists(mp) else {}
        args = [MGBA, "--script", BRIDGE, *extra_args, self.rom]
        self.proc = subprocess.Popen(args)
        deadline = time.time() + boot_timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=2)
                break
            except OSError:
                if time.time() > deadline:
                    self.close()
                    raise RuntimeError("mGBA bridge did not come up")
                time.sleep(0.25)
        self.sock.settimeout(120)
        self.f = self.sock.makefile("r")
        assert self.cmd("ping") == "pong"

    # --- transport ---
    def cmd(self, line):
        self.sock.sendall((line + "\n").encode())
        r = self.f.readline().strip()
        if not r.startswith("ok"):
            raise RuntimeError(f"{line!r} -> {r!r}")
        return r[3:]

    # --- input / time ---
    def press(self, keys, frames=4, release=4):
        self.cmd(f"press {keys} {frames}")
        if release:
            self.wait(release)

    def wait(self, frames):
        self.cmd(f"wait {frames}")

    def mash(self, keys="A", times=10, gap=20):
        for _ in range(times):
            self.press(keys, 3, gap)

    def shot(self, path):
        self.cmd(f"shot {os.path.abspath(path)}")
        return path

    def frame(self):
        return int(self.cmd("frame"))

    # --- memory ---
    def read8(self, a): return int(self.cmd(f"read8 {a:x}"))
    def read16(self, a): return int(self.cmd(f"read16 {a:x}"))
    def read32(self, a): return int(self.cmd(f"read32 {a:x}"))
    def readrange(self, a, n): return bytes.fromhex(self.cmd(f"readrange {a:x} {n}"))

    def location(self):
        """(mapGroup, mapNum, x, y) from SaveBlock1, or None before a save is loaded."""
        sb1 = self.read32(self.sym["gSaveBlock1Ptr"])
        if not (0x02000000 <= sb1 < 0x02040000):
            return None
        raw = self.readrange(sb1, 6)
        x = int.from_bytes(raw[0:2], "little", signed=True)
        y = int.from_bytes(raw[2:4], "little", signed=True)
        return (raw[4], raw[5], x, y)

    # --- game state (pokeemerald layouts) ---
    OBJECT_EVENT_SIZE = 0x24
    MAP_OFFSET = 7

    def callback2(self):
        return self.read32(self.sym["gMain"] + 4) & ~1

    def in_overworld(self):
        return self.callback2() == self.sym["CB2_Overworld"]

    def player(self):
        """(mapGroup, mapNum, x, y) using the live player object, or None."""
        loc = self.location()
        if loc is None:
            return None
        oid = self.read8(self.sym["gPlayerAvatar"] + 5)
        raw = self.readrange(self.sym["gObjectEvents"] + oid * self.OBJECT_EVENT_SIZE + 0x10, 4)
        x = int.from_bytes(raw[0:2], "little", signed=True) - self.MAP_OFFSET
        y = int.from_bytes(raw[2:4], "little", signed=True) - self.MAP_OFFSET
        return (loc[0], loc[1], x, y)

    def wait_until(self, pred, max_frames=3600, step=10):
        for _ in range(0, max_frames, step):
            if pred():
                return True
            self.wait(step)
        return False

    def boot_to_overworld(self, max_tries=200):
        """From power-on, press through title/menu (CONTINUE) until the overworld runs."""
        for i in range(max_tries):
            if self.in_overworld():
                self.wait(30)
                return True
            self.press("START" if i % 2 else "A", 3, 25)
        return False

    def boot_new_game(self, max_tries=300):
        """Fresh game via expansion Quickstart: SELECT skips the intro, then SELECT on the title."""
        for _ in range(max_tries):
            if self.in_overworld():
                self.wait(60)
                return True
            self.press("SELECT", 3, 15)
        return False

    def map_name(self, loc=None):
        if not hasattr(self, "_names"):
            self._names = load_map_names()
        loc = loc or self.player()
        return self._names.get((loc[0], loc[1]), f"?{loc[0]}.{loc[1]}") if loc else None

    def warp(self, map_name, x, y, timeout_frames=600):
        """Warp anywhere via the in-game dev mailbox (DEBUG_DEV_BRIDGE). map_name is the folder
        name (e.g. 'Route203_1'). Returns the player position after arrival."""
        if "gDevBridge" not in self.sym:
            raise RuntimeError("ROM has no gDevBridge (release build, or DEBUG_DEV_BRIDGE off)")
        if not hasattr(self, "_names"):
            self._names = load_map_names()
        const = None
        mj = os.path.join(REPO, "data", "maps", map_name, "map.json")
        if os.path.exists(mj):
            import json
            const = json.load(open(mj, encoding="utf-8"))["id"][4:]
        loc = next((k for k, v in self._names.items() if v == const), None)
        if loc is None:
            raise ValueError(f"unknown map {map_name}")
        base = self.sym["gDevBridge"]
        done = self.read32(base + 8)
        for off, val in ((4, loc[0]), (5, loc[1]), (6, x & 0xFF), (7, y & 0xFF)):
            self.cmd(f"write8 {base + off:x} {val}")
        self.cmd(f"write32 {base:x} {0x57415250}")       # 'WARP' -- written last
        if not self.wait_until(lambda: self.read32(base + 8) != done, timeout_frames, 5):
            raise RuntimeError(f"warp to {map_name} not serviced (player not in free overworld control?)")
        self.wait(10)
        self.wait_until(self.in_overworld, timeout_frames, 10)
        self.wait_for_control(timeout_frames)
        pos = self.player()
        if (pos[0], pos[1]) != loc:
            raise RuntimeError(f"warp to {map_name} ({x},{y}) landed on another map: {pos}")
        # Landing on a door/arrow tile makes the player step out of it (vanilla behaviour),
        # so the final position can differ from (x, y); callers can compare if they care.
        return pos

    def wait_for_control(self, timeout_frames=900, settle=4):
        """Block until the player has free overworld control (gDevBridge.controlFrames advances),
        i.e. fades, map loads, and scripts have finished. Precise, unlike fixed delays."""
        addr = self.sym["gDevBridge"] + 16
        start = self.read32(addr)
        if not self.wait_until(lambda: self.read32(addr) >= start + settle, timeout_frames, 2):
            raise RuntimeError("player never regained control (script/battle/menu active?)")

    def set_flag(self, flag_id, value=True, timeout_frames=300):
        """Set/clear a game flag via the dev mailbox (needs free overworld control)."""
        base = self.sym["gDevBridge"]
        done = self.read32(base + 8)
        self.cmd(f"write16 {base + 12:x} {flag_id}")
        self.cmd(f"write16 {base + 14:x} {1 if value else 0}")
        self.cmd(f"write32 {base:x} {0x464C4147}")       # 'FLAG'
        if not self.wait_until(lambda: self.read32(base + 8) != done, timeout_frames, 2):
            raise RuntimeError("flag request not serviced")

    def give_mon(self, species, level=5, timeout_frames=300):
        """Add a Pokémon to the player's party via the dev mailbox. species: 'BIDOOF' or an id."""
        if isinstance(species, str):
            if species.upper() not in species_ids():
                raise ValueError(f"unknown species {species}")
            species = species_ids()[species.upper()]
        base = self.sym["gDevBridge"]
        done = self.read32(base + 8)
        self.cmd(f"write16 {base + 12:x} {species}")
        self.cmd(f"write16 {base + 14:x} {level}")
        self.cmd(f"write32 {base:x} {0x47495645}")       # 'GIVE'
        if not self.wait_until(lambda: self.read32(base + 8) != done, timeout_frames, 2):
            raise RuntimeError("give request not serviced")

    def party_count(self):
        return self.read8(self.read32(self.sym["gPlayerPartyCountPtr"]))

    def has_control(self, frames=8):
        """True if the player has free overworld control (controlFrames advances)."""
        addr = self.sym["gDevBridge"] + 16
        start = self.read32(addr)
        self.wait(frames)
        return self.read32(addr) > start

    def flee_battle(self, max_tries=600):
        """Run from a wild battle: RUN is bottom-right of the action menu. B clears messages.
        Returns once the overworld is back and the player has control. The field is checked
        before every single press, so no stray direction reaches the overworld."""
        seq = (("RIGHT", 3), ("DOWN", 3), ("A", 12), ("B", 12))
        for i in range(max_tries * len(seq)):
            if self.in_overworld():
                break
            key, gap = seq[i % len(seq)]
            self.press(key, 3, gap)
        self.wait_for_control()

    def win_battle(self, max_presses=900):
        """Fight a battle the party can win by using its first move every turn: A picks FIGHT and
        the move and advances text; the B in each round declines 'switch Pokémon?' (it leaves the
        party menu) and is harmless elsewhere. Returns once the overworld is back with control."""
        seq = ("A", "A", "B")
        for i in range(max_presses):
            if self.in_overworld():
                break
            self.press(seq[i % len(seq)], 3, 12)
        else:
            raise RuntimeError("the battle never ended")
        self.wait_for_control()

    def facing(self):
        """The player's facing direction: 'S', 'N', 'W' or 'E' (ObjectEvent.facingDirection)."""
        oid = self.read8(self.sym["gPlayerAvatar"] + 5)
        return {1: "S", 2: "N", 3: "W", 4: "E"}.get(
            self.read8(self.sym["gObjectEvents"] + oid * self.OBJECT_EVENT_SIZE + 0x18) & 0xF)

    def object_at(self, x, y):
        """True if an active object event (not the player) stands on map tile (x, y)."""
        me = self.read8(self.sym["gPlayerAvatar"] + 5)
        for i in range(16):                          # OBJECT_EVENTS_COUNT
            base = self.sym["gObjectEvents"] + i * self.OBJECT_EVENT_SIZE
            if i == me or not self.read8(base) & 1:   # active: bit 0 of the first flags byte
                continue
            raw = self.readrange(base + 0x10, 4)
            ox = int.from_bytes(raw[0:2], "little", signed=True) - self.MAP_OFFSET
            oy = int.from_bytes(raw[2:4], "little", signed=True) - self.MAP_OFFSET
            if (ox, oy) == (x, y):
                return True
        return False

    def in_battle(self):
        return self.callback2() in (self.sym["BattleMainCB2"], self.sym["CB2_InitBattle"])

    def settle(self, timeout_frames=900):
        """After the overworld was lost mid-walk: wait until it is clear what happened.
        Returns 'battle' (a battle is running) or 'field' (a warp/transition finished and the
        player has control again). Presses nothing."""
        for _ in range(timeout_frames // 5):
            if self.in_battle():
                return "battle"
            if self.in_overworld() and self.has_control(4):
                return "field"
            self.wait(1)
        raise RuntimeError(f"neither a battle nor free control after {timeout_frames} frames "
                           f"(callback2={self.callback2():#x})")

    def advance_text(self, key="B", max_presses=400, wait_for_lock=60):
        """Press `key` until the player has control again (B closes message boxes without
        re-talking to the NPC in front). Returns the number of presses.
        First waits up to `wait_for_lock` frames for a script to take control, so a call that
        comes a frame before a triggered script starts doesn't return immediately."""
        for _ in range(wait_for_lock // 4):
            if not self.has_control(4):
                break
        else:
            return 0                     # nothing took control: no text to advance
        for i in range(max_presses):
            if self.in_overworld() and self.has_control():
                return i
            self.press(key, 3, 10)
        raise RuntimeError("text never finished (stuck in a menu or script?)")

    def mon0(self, set_hp=None, timeout_frames=300):
        """(hp, maxHp) of party slot 0 via the dev mailbox; set_hp first sets its HP."""
        base = self.sym["gDevBridge"]
        done = self.read32(base + 8)
        self.cmd(f"write16 {base + 14:x} {0xFFFF if set_hp is None else set_hp}")
        self.cmd(f"write32 {base:x} {0x4D4F4E30}")       # 'MON0'
        if not self.wait_until(lambda: self.read32(base + 8) != done, timeout_frames, 2):
            raise RuntimeError("MON0 request not serviced")
        return self.read16(base + 20), self.read16(base + 22)

    def teach_move(self, move, slot=0, timeout_frames=300):
        """Teach party slot 0 a move (dev mailbox 'MOVE'), e.g. teach_move('SURF')."""
        if isinstance(move, str):
            move = move_ids()[move.upper()]
        base = self.sym["gDevBridge"]
        done = self.read32(base + 8)
        self.cmd(f"write16 {base + 12:x} {move}")
        self.cmd(f"write16 {base + 14:x} {slot}")
        self.cmd(f"write32 {base:x} {0x4D4F5645}")       # 'MOVE'
        if not self.wait_until(lambda: self.read32(base + 8) != done, timeout_frames, 2):
            raise RuntimeError("MOVE request not serviced")

    PLAYER_AVATAR_FLAG_SURFING = 1 << 3

    def surfing(self):
        return bool(self.read8(self.sym["gPlayerAvatar"]) & self.PLAYER_AVATAR_FLAG_SURFING)

    def start_surf(self, max_presses=40):
        """Facing surfable water with a Surf user in the party (and the badge flag set): press A,
        answer YES, and wait until the player is surfing with control. Returns True on success."""
        self.press("A", 3, 30)
        for _ in range(max_presses):
            if self.surfing() and self.in_overworld() and self.has_control():
                return True
            self.press("A", 3, 20)
        return False

    def test_mode(self, trainer_sight=False):
        """Movement-only testing: no wild encounters or trainer sight (expansion config flags),
        and story gates open (FLAG_SYS_POKEMON_GET: e.g. HomeTown's 'get a Pokémon first' exit).
        Call it before entering the map whose gate should be open (gates are armed on load).
        trainer_sight=True leaves trainers able to see the player (event tests)."""
        cfgs = [("include/config/wild_encounter.h", "WE_FLAG_NO_ENCOUNTER")]
        if not trainer_sight:
            cfgs.append(("include/config/overworld.h", "OW_FLAG_NO_TRAINER_SEE"))
        for cfg, name in cfgs:
            flag = config_flag(cfg, name)
            if flag:
                self.set_flag(flag)
        self.set_flag(flag_id("FLAG_SYS_POKEMON_GET"))

    def step(self, direction, n=1):
        """Walk n tiles; returns the player position afterwards."""
        for _ in range(n):
            self.press(direction, 16, 2)
        self.wait(10)
        return self.player()

    # --- lifecycle ---
    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.kill()

    def __enter__(self): return self
    def __exit__(self, *a): self.close()
