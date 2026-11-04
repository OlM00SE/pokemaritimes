"""Play the latest build by hand, in your own mGBA, with a save that loads.

  python dev/play.py              # copy the latest ROM to the play folder, check the save, launch
  python dev/play.py --build      # run dev/fastbuild.py first ("Play PokeMaritimes.bat" does this)
  python dev/play.py --new        # set the current save aside and start a fresh game
  python dev/play.py --check      # only report the build and the save; change nothing

The play folder is RomHackDev/playtest, outside the repo, so builds, tests and git never touch it:
  PokeMaritimes.gba, .map   the ROM you play: a copy of pokeemerald.gba, refreshed at each launch
  PokeMaritimes.sav         your save (mGBA keeps it beside the ROM), plus any save states
  build.txt                 which commit and save layout the ROM was built from
  old_saves/<when>_<why>/   saves set aside; nothing is ever deleted
A save this build can't load (dev/savefile.py: an older save layout, or damage) is set aside with
its save states before launching, so the game starts clean instead of calling it corrupt.

mGBA: the installed one (found in the registry; MGBA_PLAY_EXE overrides it), so your keys and
settings apply; failing that, the dev build in tools/mgba/mgba-dev.
"""
import argparse, datetime, filecmp, glob, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import REPO, MGBA as DEV_MGBA
import save_layout, savefile

PLAY = os.path.normpath(os.path.join(REPO, "..", "..", "playtest"))
NAME = "PokeMaritimes"
ROM, SAV = os.path.join(PLAY, NAME + ".gba"), os.path.join(PLAY, NAME + ".sav")


def find_mgba():
    if os.environ.get("MGBA_PLAY_EXE"):
        return os.environ["MGBA_PLAY_EXE"]
    import winreg
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            root = winreg.OpenKey(hive, key)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                if not str(winreg.QueryValueEx(sub, "DisplayName")[0]).lower().startswith("mgba"):
                    continue
                exe = os.path.join(winreg.QueryValueEx(sub, "InstallLocation")[0], "mGBA.exe")
                if os.path.exists(exe):
                    return exe
            except OSError:
                continue
    return DEV_MGBA


def already_open():
    """True if an mGBA has the play ROM open (moving its save or ROM under it would lose play)."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name like 'mGBA%'\" | ForEach-Object CommandLine"],
                       capture_output=True, text=True)
    return any(NAME.lower() + ".gba" in line.lower() for line in r.stdout.splitlines())


def set_aside(tag, why):
    """Move the save and its save states to old_saves/<when>_<tag>/ (never overwriting)."""
    files = [p for p in [SAV] + glob.glob(os.path.join(PLAY, NAME + ".ss*")) if os.path.exists(p)]
    if not files:
        return None
    stamp = datetime.datetime.fromtimestamp(os.path.getmtime(files[0])).strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(PLAY, "old_saves", f"{stamp}_{tag}")
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(PLAY, "old_saves", f"{stamp}_{tag}_{n}")
    os.makedirs(dest)
    for p in files:
        shutil.move(p, dest)
    with open(os.path.join(dest, "why.txt"), "w", encoding="utf-8") as f:
        f.write(why + "\n")
    return dest


def build_info():
    rec = save_layout.recorded()
    head = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%h %s"],
                          capture_output=True, text=True).stdout.strip()
    built = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(REPO, "pokeemerald.gba")))
    return (f"built {built:%Y-%m-%d %H:%M} from {head or '(unknown commit)'}\n"
            f"save layout version {rec['SAVE_LAYOUT_VERSION']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true", help="run dev/fastbuild.py first")
    ap.add_argument("--new", action="store_true", help="set the current save aside: start fresh")
    ap.add_argument("--check", action="store_true", help="report only; copy, move and launch nothing")
    a = ap.parse_args()

    if a.build and not a.check:
        import fastbuild
        if fastbuild.main([]) != 0:
            print("\nThe build failed, so the ROM is the previous build.")
            if not sys.stdin.isatty():
                return 1
            input("Press Enter to play the previous build anyway, or close this window. ")
    src = os.path.join(REPO, "pokeemerald.gba")
    if not os.path.exists(src):
        sys.exit("no pokeemerald.gba: run python dev/fastbuild.py first")
    os.makedirs(PLAY, exist_ok=True)
    info = build_info()
    print("ROM:", info.replace("\n", "; "))

    verdict, why = savefile.check(SAV)
    print(f"save: {SAV}\n      {verdict}: {why}")
    if a.check:
        return 0
    if already_open():
        print("\nPokeMaritimes is already open in mGBA. Close it (save in-game first), then run this again.")
        return 1

    if a.new or verdict == "stale":
        dest = set_aside("set-aside" if a.new else "old-layout",
                         "set aside by dev/play.py --new" if a.new else f"this build can't load it: {why}")
        if dest:
            print(f"      moved to {dest}; the game starts with no save (NEW GAME)")
    elif verdict == "warn":
        print("      kept: the game will say the save is corrupted and load the previous one")

    for ext in (".gba", ".map"):
        s, d = os.path.join(REPO, "pokeemerald" + ext), os.path.join(PLAY, NAME + ext)
        if os.path.exists(s) and not (os.path.exists(d) and filecmp.cmp(s, d, shallow=False)):
            shutil.copyfile(s, d)
    with open(os.path.join(PLAY, "build.txt"), "w", encoding="utf-8") as f:
        f.write(info + "\n")

    exe = find_mgba()
    print(f"launching {exe}\n       {ROM}")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe, ROM], cwd=PLAY, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
