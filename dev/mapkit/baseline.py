"""Known, explained ERRORs on vanilla maps (the checker's regression baseline).

Vanilla Emerald maps are known to work, so every ERROR the checker reports on them is
either a modelling gap or a deliberate special case. The special cases are listed here
with their reason; anything else on a vanilla map is a checker bug to investigate.
`python dev/check_maps.py --baseline` verifies the corpus against this list.
"""

KNOWN = {
    # Battle Palace: the player is moved by scripts; decorative water and doors are never walked.
    ("BattleFrontier_BattlePalaceBattleRoom", "water"): "scripted movement, decorative water",
    ("BattleFrontier_BattlePalaceCorridor", "water"): "scripted movement, decorative water",
    ("BattleFrontier_BattlePalaceCorridor", "reach"): "doors used by scripted movement",
    ("BattleFrontier_BattlePalaceLobby", "reach"): "door used by scripted movement",
    # Arrival points on water: the player arrives surfing (Sky Pillar exit / Aqua Hideout sub dock).
    ("AquaHideout_1F", "warp"): "arrival-only warp on water (player arrives surfing)",
    ("Route131", "warp"): "arrival-only warp on water (exit from Sky Pillar, player arrives surfing)",
}
