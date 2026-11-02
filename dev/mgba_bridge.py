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
