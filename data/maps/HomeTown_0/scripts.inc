HomeTown_0_MapScripts::
# 7 "data/maps/HomeTown_0/scripts.pory"
	map_script MAP_SCRIPT_ON_TRANSITION, HomeTown_0_MapScripts_MAP_SCRIPT_ON_TRANSITION
	.byte 0

HomeTown_0_MapScripts_MAP_SCRIPT_ON_TRANSITION:
# 9 "data/maps/HomeTown_0/scripts.pory"
	goto_if_set FLAG_SYS_POKEMON_GET, HomeTown_0_MapScripts_MAP_SCRIPT_ON_TRANSITION_1
	return

HomeTown_0_MapScripts_MAP_SCRIPT_ON_TRANSITION_1:
# 10 "data/maps/HomeTown_0/scripts.pory"
	setvar VAR_TEMP_1, 1
	return


HomeTown_EventScript_Researcher::
# 16 "data/maps/HomeTown_0/scripts.pory"
	lock
# 17 "data/maps/HomeTown_0/scripts.pory"
	faceplayer
# 18 "data/maps/HomeTown_0/scripts.pory"
	goto_if_set FLAG_SYS_POKEMON_GET, HomeTown_EventScript_Researcher_2
# 24 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_EventScript_Researcher_Text_1
# 25 "data/maps/HomeTown_0/scripts.pory"
	closemessage
# 26 "data/maps/HomeTown_0/scripts.pory"
	fadescreen FADE_TO_BLACK
# 27 "data/maps/HomeTown_0/scripts.pory"
	special ChooseStarterNoBattle
# 28 "data/maps/HomeTown_0/scripts.pory"
	setflag FLAG_SYS_POKEMON_GET
# 29 "data/maps/HomeTown_0/scripts.pory"
	setvar VAR_TEMP_1, 1
# 30 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_EventScript_Researcher_Text_2
# 31 "data/maps/HomeTown_0/scripts.pory"
	giveitem ITEM_POKE_BALL, 5
# 32 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_EventScript_Researcher_Text_3
# 33 "data/maps/HomeTown_0/scripts.pory"
	release
	end

HomeTown_EventScript_Researcher_2:
# 19 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_EventScript_Researcher_Text_0
# 20 "data/maps/HomeTown_0/scripts.pory"
	special HealPlayerParty
# 21 "data/maps/HomeTown_0/scripts.pory"
	release
	end


HomeTown_EventScript_ExitWithoutPokemon::
# 39 "data/maps/HomeTown_0/scripts.pory"
	lockall
# 40 "data/maps/HomeTown_0/scripts.pory"
	applymovement LOCALID_HOMETOWN_RESEARCHER, Common_Movement_ExclamationMark
# 41 "data/maps/HomeTown_0/scripts.pory"
	waitmovement 0
# 42 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_EventScript_ExitWithoutPokemon_Text_0
# 43 "data/maps/HomeTown_0/scripts.pory"
	closemessage
# 44 "data/maps/HomeTown_0/scripts.pory"
	applymovement LOCALID_PLAYER, HomeTown_Movement_StepBack
# 45 "data/maps/HomeTown_0/scripts.pory"
	waitmovement 0
# 46 "data/maps/HomeTown_0/scripts.pory"
	releaseall
	end


# 50 "data/maps/HomeTown_0/scripts.pory"
HomeTown_Movement_StepBack:
# 51 "data/maps/HomeTown_0/scripts.pory"
	walk_up
	step_end

HomeTown_0_EventScript_PlayersMailbox::
# 58 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_0_EventScript_PlayersMailbox_Text_0, MSGBOX_SIGN
	end


HomeTown_0_EventScript_NeighboursMailbox::
# 63 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_0_EventScript_NeighboursMailbox_Text_0, MSGBOX_SIGN
	end


HomeTown_0_EventScript_Neighbour::
# 68 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_0_EventScript_Neighbour_Text_0, MSGBOX_NPC
	end


HomeTown_0_EventScript_MillHand::
# 73 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_0_EventScript_MillHand_Text_0, MSGBOX_NPC
	end


HomeTown_0_EventScript_Boy::
# 78 "data/maps/HomeTown_0/scripts.pory"
	msgbox HomeTown_0_EventScript_Boy_Text_0, MSGBOX_NPC
	end


HomeTown_EventScript_Researcher_Text_0:
# 19 "data/maps/HomeTown_0/scripts.pory"
	.string "Let me check on your Pokémon... There,\n"
	.string "all rested up!\p"
	.string "The wildlife station is in Woodstock,\n"
	.string "just down Route 201.$"

HomeTown_EventScript_Researcher_Text_1:
# 24 "data/maps/HomeTown_0/scripts.pory"
	.string "Oh, hello! I'm a field researcher from\n"
	.string "the wildlife station in Woodstock.\p"
	.string "I'm surveying the Pokémon that live in\n"
	.string "these woods.\p"
	.string "Heading out on Route 201? Wild Pokémon\n"
	.string "hide in the tall grass, so you'll want a\l"
	.string "partner.\p"
	.string "Here, choose one of these!$"

HomeTown_EventScript_Researcher_Text_2:
# 30 "data/maps/HomeTown_0/scripts.pory"
	.string "Take these Poké Balls too, so you can\n"
	.string "catch Pokémon of your own.$"

HomeTown_EventScript_Researcher_Text_3:
# 32 "data/maps/HomeTown_0/scripts.pory"
	.string "If your Pokémon get tired, come back\n"
	.string "and see me. Good luck out there!$"

HomeTown_EventScript_ExitWithoutPokemon_Text_0:
# 42 "data/maps/HomeTown_0/scripts.pory"
	.string "Wait! Wild Pokémon live in the tall grass\n"
	.string "on Route 201.\p"
	.string "It isn't safe without a Pokémon of your\n"
	.string "own. Come talk to me first!$"

HomeTown_0_EventScript_PlayersMailbox_Text_0:
# 58 "data/maps/HomeTown_0/scripts.pory"
	.string "{PLAYER}'s HOUSE$"

HomeTown_0_EventScript_NeighboursMailbox_Text_0:
# 63 "data/maps/HomeTown_0/scripts.pory"
	.string "LEBLANC$"

HomeTown_0_EventScript_Neighbour_Text_0:
# 68 "data/maps/HomeTown_0/scripts.pory"
	.string "Good morning, dear! The beans are\n"
	.string "coming along nicely this year.\p"
	.string "In the spring we pick fiddleheads down\n"
	.string "by the brook. Nothing tastes better\l"
	.string "with a bit of butter.$"

HomeTown_0_EventScript_MillHand_Text_0:
# 73 "data/maps/HomeTown_0/scripts.pory"
	.string "Most folks in the village work in the\n"
	.string "woods or down at the sawmill.\p"
	.string "Spruce and fir, mostly. The trees around\n"
	.string "here grow straight and tall.$"

HomeTown_0_EventScript_Boy_Text_0:
# 78 "data/maps/HomeTown_0/scripts.pory"
	.string "That researcher from Woodstock comes\n"
	.string "up every week to check on the Pokémon\l"
	.string "in the woods.\p"
	.string "When I'm big, I'm going to walk all the\n"
	.string "way to Woodstock by myself!$"
