"""In-game: wild battles on a map's grass happen, and only species from its land table appear.

  python dev/tests/ingame_encounters.py Route201_1 [--battles 12]
  python dev/tests/ingame_encounters.py Route201_1 --no-party    # no battles without a party
Gives the player a level-50 Pokémon via the dev bridge, paces on a grass tile until a battle
starts, reads the opponent's species from gBattleMons[1], runs, and repeats.
Exit code 1 if no battle starts or a species outside the table appears.
"""
import collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED, species_ids
from playtest import prepare_rom
from mapkit.project import Project, TILE_FLAG_HAS_ENCOUNTERS, TILE_FLAG_SURFABLE

PLAYER_MON = "STARLY"


def land_table(p, map_id):
    data = json.load(open(p.path("src/data/wild_encounters.json"), encoding="utf-8"))
    for e in data["wild_encounter_groups"][0]["encounters"]:
        if e.get("map") == map_id and "land_mons" in e:
            return [m["species"][8:] for m in e["land_mons"]["mons"]]
    return []


def grass_pair(p, name):
    """Two horizontally adjacent walkable grass tiles to pace between."""
    L = p.load_map(name).layout
    def grass(x, y):
        f = p.tile_flags.get(L.tiles.behavior(L.mid(x, y)), 0)
        return f & TILE_FLAG_HAS_ENCOUNTERS and not f & TILE_FLAG_SURFABLE and not L.coll(x, y)
    for y in range(L.height):
        for x in range(L.width - 1):
            if grass(x, y) and grass(x + 1, y):
                return x, y
    return None


def battle_mon_size(e):
    """sizeof(struct BattlePokemon) from the linker map: gBattleMons spans 4 battlers."""
    base = e.sym["gBattleMons"]
    nxt = min(a for a in e.sym.values() if a > base)
    span = nxt - base
    if span % 4 or not 64 <= span // 4 <= 256:
        raise RuntimeError(f"gBattleMons spans {span} bytes; cannot infer sizeof(BattlePokemon)")
    return span // 4


def main(argv):
    name = argv[0]
    battles = int(argv[argv.index("--battles") + 1]) if "--battles" in argv else 12
    p = Project()
    map_id = p.load_map(name).id
    table = land_table(p, map_id)
    if not table:
        print(f"{name} has no land encounter table"); return 1
    ids = {v: k for k, v in species_ids().items()}
    spot = grass_pair(p, name)
    if spot is None:
        print(f"{name}: no two side-by-side walkable grass tiles to pace on"); return 1
    seen, fails = collections.Counter(), []
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        if "--no-party" in argv:      # guard check: no wild battles before the player has a Pokémon
            assert e.party_count() == 0
            e.warp(name, *spot)
            for steps in range(300):
                e.press("RIGHT" if steps % 2 == 0 else "LEFT", 16, 2)
                if not e.in_overworld():
                    print(f"FAIL: wild battle with an empty party after {steps + 1} steps")
                    e.shot(os.path.join(REPO, "dev", "out", f"encounter_noparty_{name}.png"))
                    return 1
            print("RESULT: PASS (300 grass steps with an empty party, no battle)")
            return 0
        e.give_mon(PLAYER_MON, 50)
        assert e.party_count() == 1, "dev bridge GIVE did not add a Pokémon"
        size = battle_mon_size(e)
        e.warp(name, *spot)
        for b in range(battles):
            steps = 0
            while e.in_overworld() and steps < 400:
                e.press("RIGHT" if steps % 2 == 0 else "LEFT", 16, 2)
                steps += 1
            if e.in_overworld():
                fails.append(f"no battle after {steps} steps"); break
            # wait for the battle to set up both battlers
            e.wait_until(lambda: e.read16(e.sym["gBattleMons"]) != 0 and e.read16(e.sym["gBattleMons"] + size) != 0, 1200, 10)
            player_sp = ids.get(e.read16(e.sym["gBattleMons"]), "?")
            wild = ids.get(e.read16(e.sym["gBattleMons"] + size), "?")
            if b == 0:
                e.shot(os.path.join(REPO, "dev", "out", f"encounter_{name}.png"))
            if player_sp != PLAYER_MON:
                fails.append(f"battle {b}: gBattleMons[0] is {player_sp}, expected {PLAYER_MON} (bad offset?)"); break
            seen[wild] += 1
            print(f"battle {b + 1}: wild {wild} after {steps} steps")
            # Run. flee_battle checks for the field before every press, so no stray direction
            # walks the player off the grass (that made this test flaky); re-warp to be sure.
            e.flee_battle()
            e.warp(name, *spot)
            # clear battle mons so the next read waits for fresh data
            e.cmd(f"write16 {e.sym['gBattleMons'] + size:x} 0")
    bad = [s for s in seen if s not in table]
    if bad:
        fails.append(f"species not in the table: {bad}")
    print("table:", ", ".join(sorted(set(table))))
    print("seen: ", dict(seen))
    for f in fails:
        print("FAIL", f)
    print("RESULT:", "PASS" if not fails else f"{len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
