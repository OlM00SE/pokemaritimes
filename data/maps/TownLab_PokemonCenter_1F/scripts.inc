TownLab_PokemonCenter_1F_MapScripts::
# 5 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	map_script MAP_SCRIPT_ON_TRANSITION, TownLab_PokemonCenter_1F_MapScripts_MAP_SCRIPT_ON_TRANSITION
# 8 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	map_script MAP_SCRIPT_ON_RESUME, CableClub_OnResume
	.byte 0

TownLab_PokemonCenter_1F_MapScripts_MAP_SCRIPT_ON_TRANSITION:
# 6 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	setrespawn HEAL_LOCATION_TOWN_LAB
	return


TownLab_PokemonCenter_1F_EventScript_Nurse::
# 13 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	setvar VAR_0x800B, LOCALID_TOWN_LAB_POKEMON_CENTER_1F_NURSE
# 14 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	call Common_EventScript_PkmnCenterNurse
# 15 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	waitmessage
# 16 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	waitbuttonpress
# 17 "data/maps/TownLab_PokemonCenter_1F/scripts.pory"
	release
	end

