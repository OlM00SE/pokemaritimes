"""Fast build: mirror the repo into WSL's native filesystem and build there.

Building directly on /mnt/e is slow (~160s even when nothing changed) because
WSL's view of Windows drives is slow to scan. The E: repo stays the single
source of truth (Porymap, git, editing all happen there). This script:
  1. seeds ~/maritimes-build in WSL once (tar copy, excludes .git/build),
  2. syncs only files changed on E: since the last sync (and deletions),
  3. runs make in the mirror,
  4. copies the ROM, .map, and generated map constants back to E:.

  python dev/fastbuild.py            # sync + build
  python dev/fastbuild.py --reseed   # rebuild the mirror from scratch
  python dev/fastbuild.py clean      # extra args go to make
"""
import json, os, shutil, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISTRO, MIRROR_LINUX = "Debian", "~/maritimes-build"
MANIFEST = os.path.join(REPO, "dev", "out", ".fastbuild_manifest.json")
SKIP_DIRS = {".git", "build", "out", "__pycache__"}     # "out" only matters under dev/
BACK = ["pokeemerald.gba", "pokeemerald.map", "include/constants/map_groups.h"]


def wsl(cmd, check=True):
    # --exec: no intermediate shell, so $?, $HOME etc. are expanded by *our* bash -c
    return subprocess.run(["wsl", "-d", DISTRO, "--exec", "bash", "-c", cmd],
                          capture_output=True, text=True, check=check)


def mirror_unc():
    home = wsl("echo $HOME").stdout.strip()
    return rf"\\wsl.localhost\{DISTRO}" + (home + "/maritimes-build").replace("/", "\\")


def scan():
    files = {}
    for root, dirs, names in os.walk(REPO):
        rel_root = os.path.relpath(root, REPO)
        dirs[:] = [d for d in dirs if not (d in SKIP_DIRS and (d != "out" or rel_root == "dev"))
                   and not (rel_root == "." and d == "build")]
        for n in names:
            p = os.path.join(root, n)
            st = os.stat(p)
            files[os.path.relpath(p, REPO).replace("\\", "/")] = [st.st_mtime_ns, st.st_size]
    return files


def to_linux(path):
    return wsl(f"wslpath -a '{path.replace(chr(92), '/')}'").stdout.strip()


def seed():
    src = to_linux(REPO)
    print("Seeding WSL mirror (one-time, a few minutes)...")
    r = wsl(f"rm -rf {MIRROR_LINUX} && mkdir -p {MIRROR_LINUX} && "
            f"tar -C '{src}' --exclude=./.git --exclude=./build --exclude=./dev/out "
            f"--exclude=./pokeemerald.gba --exclude=./pokeemerald.elf --exclude=./pokeemerald.map "
            f"--exclude='./*.sav' -cf - . | tar -C {MIRROR_LINUX} -xf - && "
            # expansion's make refuses to run without .git; this is its documented opt-out
            f"touch {MIRROR_LINUX}/.histignore", check=False)
    if r.returncode:
        sys.exit("seed failed: " + r.stderr)


def main(argv):
    t0 = time.time()
    reseed = "--reseed" in argv
    make_args = [a for a in argv if a != "--reseed"]
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    unc = mirror_unc()
    now = scan()
    if reseed or not os.path.exists(MANIFEST) or not os.path.isdir(unc):
        seed()
        changed, deleted = [], []
    else:
        old = json.load(open(MANIFEST))
        changed = [p for p, v in now.items() if old.get(p) != v]
        deleted = [p for p in old if p not in now]
        for p in changed:
            dst = os.path.join(unc, p.replace("/", "\\"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(REPO, p), dst)   # fresh mtime => make sees it
        for p in deleted:
            try:
                os.remove(os.path.join(unc, p.replace("/", "\\")))
            except FileNotFoundError:
                pass
    print(f"sync: {len(changed)} changed, {len(deleted)} deleted ({time.time() - t0:.1f}s)")
    for p in changed[:15]:
        print("   ", p)

    t1 = time.time()
    cmd = (f'export PATH="$HOME/.local/arm-gnu-toolchain/bin:$HOME/.local/bin:$PATH"; '
           f'cd {MIRROR_LINUX} && make -j"$(nproc)" {" ".join(make_args)} > ~/maritimes-build/.fastbuild.log 2>&1; '
           f'echo $?')
    out = wsl(cmd, check=False).stdout.strip().splitlines()
    code = int(out[-1]) if out and out[-1].strip().isdigit() else 99
    if code == 0 and not make_args and not os.path.exists(os.path.join(unc, "pokeemerald.gba")):
        code = 98   # make "succeeded" but produced no ROM: treat as failure
    if code != 0:
        print(wsl("grep -nE 'error|Error [0-9]' ~/maritimes-build/.fastbuild.log | head -20; tail -n 15 ~/maritimes-build/.fastbuild.log",
                  check=False).stdout)
        print(f"BUILD FAILED (make exit {code}); full log: ~/maritimes-build/.fastbuild.log in WSL")
        json.dump(now, open(MANIFEST, "w"))   # sync state is still valid
        return 1
    if not make_args:
        for p in BACK:
            src = os.path.join(unc, p.replace("/", "\\"))
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(REPO, p))
        now = scan()   # copied-back files must not bounce back next sync
    json.dump(now, open(MANIFEST, "w"))
    print(f"BUILD OK: make {time.time() - t1:.0f}s, total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
