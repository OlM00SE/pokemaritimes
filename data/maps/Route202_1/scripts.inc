Route202_1_MapScripts::
	.byte 0


Route202_1_EventScript_RouteSign::
# 8 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_RouteSign_Text_0, MSGBOX_SIGN
	end


Route202_1_EventScript_MeducticSign::
# 13 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_MeducticSign_Text_0, MSGBOX_SIGN
	end


Route202_1_EventScript_RiverWatcher::
# 18 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_RiverWatcher_Text_0, MSGBOX_NPC
	end


Route202_1_EventScript_FishermanMurray::
# 23 "data/maps/Route202_1/scripts.pory"
	trainerbattle_single TRAINER_ROUTE202_1_FISHERMAN_MURRAY, Route202_1_EventScript_FishermanMurray_Text_0, Route202_1_EventScript_FishermanMurray_Text_1
# 24 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_FishermanMurray_Text_2, MSGBOX_AUTOCLOSE
	end


Route202_1_EventScript_PicnickerAnne::
# 29 "data/maps/Route202_1/scripts.pory"
	trainerbattle_single TRAINER_ROUTE202_1_PICNICKER_ANNE, Route202_1_EventScript_PicnickerAnne_Text_0, Route202_1_EventScript_PicnickerAnne_Text_1
# 30 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_PicnickerAnne_Text_2, MSGBOX_AUTOCLOSE
	end


Route202_1_EventScript_HikerGordon::
# 35 "data/maps/Route202_1/scripts.pory"
	trainerbattle_single TRAINER_ROUTE202_1_HIKER_GORDON, Route202_1_EventScript_HikerGordon_Text_0, Route202_1_EventScript_HikerGordon_Text_1
# 36 "data/maps/Route202_1/scripts.pory"
	msgbox Route202_1_EventScript_HikerGordon_Text_2, MSGBOX_AUTOCLOSE
	end


Route202_1_EventScript_RouteSign_Text_0:
# 8 "data/maps/Route202_1/scripts.pory"
	.string "ROUTE 202\n{DOWN_ARROW} MEDUCTIC$"

Route202_1_EventScript_MeducticSign_Text_0:
# 13 "data/maps/Route202_1/scripts.pory"
	.string "MEDUCTIC\nWhere the old portage trail left the river for the Eel River lakes.$"

Route202_1_EventScript_RiverWatcher_Text_0:
# 18 "data/maps/Route202_1/scripts.pory"
	.string "Before the dam went in downriver, the\n"
	.string "Saint John ran fast and shallow here.\p"
	.string "Now it's wide and slow all the way to\n"
	.string "Meductic. The islands used to be\l"
	.string "hilltops, you know.$"

Route202_1_EventScript_FishermanMurray_Text_0:
# 23 "data/maps/Route202_1/scripts.pory"
	.string "Shh! The trout are biting in the brook\n"
	.string "today.$"

Route202_1_EventScript_FishermanMurray_Text_1:
# 23 "data/maps/Route202_1/scripts.pory"
	.string "You scared them all off...$"

Route202_1_EventScript_FishermanMurray_Text_2:
# 24 "data/maps/Route202_1/scripts.pory"
	.string "This brook comes down out of the hills\n"
	.string "and cuts right through the terraces.\p"
	.string "It's a short walk down to the big river\n"
	.string "from here.$"

Route202_1_EventScript_PicnickerAnne_Text_0:
# 29 "data/maps/Route202_1/scripts.pory"
	.string "The hay's taller than me this year! Want\n"
	.string "to battle?$"

Route202_1_EventScript_PicnickerAnne_Text_1:
# 29 "data/maps/Route202_1/scripts.pory"
	.string "My Pokémon got lost in the hay...$"

Route202_1_EventScript_PicnickerAnne_Text_2:
# 30 "data/maps/Route202_1/scripts.pory"
	.string "The flats down here flood every spring.\n"
	.string "That's why the soil grows such good hay.$"

Route202_1_EventScript_HikerGordon_Text_0:
# 35 "data/maps/Route202_1/scripts.pory"
	.string "You climbed all the way up here? Let's\n"
	.string "see what you've got!$"

Route202_1_EventScript_HikerGordon_Text_1:
# 35 "data/maps/Route202_1/scripts.pory"
	.string "Whew! You're tougher than this hill.$"

Route202_1_EventScript_HikerGordon_Text_2:
# 36 "data/maps/Route202_1/scripts.pory"
	.string "From the top of the valley wall you can\n"
	.string "see the river swing east at Meductic.\p"
	.string "The cliffs across the water are the far\n"
	.string "bank. Nobody gets over there without a\l"
	.string "boat.$"
