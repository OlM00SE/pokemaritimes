Route201_1_MapScripts::
	.byte 0


Route201_1_EventScript_RouteSign::
# 8 "data/maps/Route201_1/scripts.pory"
	msgbox Route201_1_EventScript_RouteSign_Text_0, MSGBOX_SIGN
	end


Route201_1_EventScript_Forester::
# 13 "data/maps/Route201_1/scripts.pory"
	msgbox Route201_1_EventScript_Forester_Text_0, MSGBOX_NPC
	end


Route201_1_EventScript_BugCatcherRoss::
# 18 "data/maps/Route201_1/scripts.pory"
	trainerbattle_single TRAINER_ROUTE201_1_BUG_CATCHER_ROSS, Route201_1_EventScript_BugCatcherRoss_Text_0, Route201_1_EventScript_BugCatcherRoss_Text_1
# 19 "data/maps/Route201_1/scripts.pory"
	msgbox Route201_1_EventScript_BugCatcherRoss_Text_2, MSGBOX_AUTOCLOSE
	end


Route201_1_EventScript_RouteSign_Text_0:
# 8 "data/maps/Route201_1/scripts.pory"
	.string "ROUTE 201\n{RIGHT_ARROW} WOODSTOCK$"

Route201_1_EventScript_Forester_Text_0:
# 13 "data/maps/Route201_1/scripts.pory"
	.string "We logged this stand a few summers\n"
	.string "back. Look at those saplings, already\l"
	.string "up to my shoulder!\p"
	.string "Pokémon like the young woods. The tall\n"
	.string "grass between the saplings is full of\l"
	.string "them.$"

Route201_1_EventScript_BugCatcherRoss_Text_0:
# 18 "data/maps/Route201_1/scripts.pory"
	.string "Hey! You jumped right into my\n"
	.string "bug-catching spot!$"

Route201_1_EventScript_BugCatcherRoss_Text_1:
# 18 "data/maps/Route201_1/scripts.pory"
	.string "Aww, my bugs got squashed...$"

Route201_1_EventScript_BugCatcherRoss_Text_2:
# 19 "data/maps/Route201_1/scripts.pory"
	.string "Bug Pokémon love the meadow up on the\n"
	.string "slope.\p"
	.string "I come here every day after school.$"
