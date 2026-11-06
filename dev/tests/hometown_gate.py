"""HomeTown's exit gate covers every way out (no emulator; the engine model).

  python dev/tests/hometown_gate.py

A new player without a Pokémon is called back by the researcher when they step onto one of the
gate's trigger tiles (coord events running HomeTown_EventScript_ExitWithoutPokemon). The gate only
works if every way out of the hamlet crosses one. On the model (mapkit/engine.py, people at home):
  * from the lane below the player's door, with the trigger tiles closed, no walk reaches a
    connection's edge (Route 201, or any other neighbour);
  * control: with the triggers open, the walk does reach Route 201 (the search isn't vacuous);
  * control: each trigger is needed: closing all the others leaves a way out through it (a tile
    no path uses would be a sign that the gate sits in the wrong place);
  * each trigger's step back (the script walks the player left) lands on a walkable tile, so the
    player isn't left standing on the trigger, free to go on;
  * each trigger fires for a player standing there: a coord event runs only when its elevation is
    the player's (the tile's) or 0, any (field_control_avatar.c, TryStartCoordEventScript), so a
    trigger on a tile of another elevation would be closed here but open in the game.
Exit 1 on a failure. A redesign of HomeTown that opens a new gap fails here before it fails in the
playthrough.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.events import world_with_people
from mapkit.routes import _search

MAP = "HomeTown_0"
SCRIPT = "HomeTown_EventScript_ExitWithoutPokemon"
START = (9, 15)          # the lane below the player's doormat (also the world revision's safe tile)
STEP_BACK = (-1, 0)      # HomeTown_Movement_StepBack: walk_left


def escapes(p, m, closed_tiles):
    """Edges of neighbours reached from START with closed_tiles (map coords) closed."""
    world = world_with_people(p, m, boxes=False, extra=set(closed_tiles), permanent_only=True)
    # guard: the closed tiles really are obstacles in the model (extra takes map coordinates; a
    # wrong frame would close nothing and every check below would pass without testing anything)
    shut = {world.to_grid(x, y) for x, y in closed_tiles}
    assert shut <= set(world.obstacles), f"closed tiles not obstacles: {sorted(shut - set(world.obstacles))[:3]}"
    got = _search(world, [world.arrival_state(*world.to_grid(*START))], False, lambda gx, gy: False)
    assert got is not None, "search too big"
    return {world.conn_side.get((s[0], s[1])) for s in got if not world.in_map(s[0], s[1])} - {None}


def main():
    p = Project()
    m = p.load_map(MAP)
    triggers = [(c["x"], c["y"]) for c in m.events("coord_events") if c.get("script") == SCRIPT]
    fails = 0

    def check(ok, msg):
        nonlocal fails
        print(("PASS: " if ok else "FAIL: ") + msg)
        fails += not ok

    check(len(triggers) > 0, f"{len(triggers)} gate trigger tiles on {MAP}")
    if not triggers:
        return 1
    check(escapes(p, m, []) != set(), "control: with the gate open, a walk from the lane leaves the hamlet")
    out = escapes(p, m, triggers)
    check(out == set(), f"with the gate's tiles closed, nothing leaves the hamlet (reached: {sorted(out) or 'none'})")
    for t in triggers:
        others = [o for o in triggers if o != t]
        check(escapes(p, m, others) != set(), f"trigger {t} is needed: without the others, a way out crosses it")
    L = m.layout
    for c in m.events("coord_events"):
        if c.get("script") == SCRIPT:
            x, y, e = c["x"], c["y"], int(c["elevation"])
            tile = L.get(x, y) >> 12
            check(e in (0, tile), f"trigger {(x, y)} fires there: its elevation {e}, the tile's {tile}")
    world = world_with_people(p, m, boxes=False, permanent_only=True)
    for x, y in triggers:
        bx, by = x + STEP_BACK[0], y + STEP_BACK[1]
        g = world.to_grid(bx, by)
        ok = (world.in_map(*g) and world.collision(*g) == 0 and g not in world.obstacles
              and (bx, by) not in triggers)
        check(ok, f"the step back from {(x, y)} lands on walkable {(bx, by)}")
    print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
