"""Two live mGBA sessions must keep separate bridges and leave each other responsive.

  python dev/tests/emulator_isolation.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED


def main():
    out = os.path.join(REPO, "dev", "out")
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bridge-isolation-", dir=out,
                                     ignore_cleanup_errors=True) as folder:
        paths = []
        for name in ("one", "two"):
            rom = os.path.join(folder, name + ".gba")
            shutil.copyfile(os.path.join(REPO, "pokeemerald.gba"), rom)
            shutil.copyfile(os.path.join(REPO, "pokeemerald.map"), rom[:-4] + ".map")
            paths.append(rom)
        with Emu(paths[0], extra_args=UNTHROTTLED) as first:
            assert first.boot_new_game(), "first emulator did not reach the overworld"
            before = first.player()
            with Emu(paths[1], extra_args=UNTHROTTLED) as second:
                assert second.boot_new_game(), "second emulator did not reach the overworld"
                assert first.port != second.port and first.session != second.session
                assert first.cmd("ping") == f"pong {first.session}"
                assert second.cmd("ping") == f"pong {second.session}"
                assert first.player() == before, "second emulator changed the first session"
                assert second.player() == before, "second emulator did not boot independently"
            first.wait(10)
            assert first.player() == before, "closing the second emulator disrupted the first"
    print("PASS: two simultaneous mGBA bridges and ROM copies stayed independent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
