TownLab_Mart_MapScripts::
	.byte 0


TownLab_Mart_EventScript_Clerk::
# 9 "data/maps/TownLab_Mart/scripts.pory"
	lock
# 10 "data/maps/TownLab_Mart/scripts.pory"
	faceplayer
# 11 "data/maps/TownLab_Mart/scripts.pory"
	message gText_HowMayIServeYou
# 12 "data/maps/TownLab_Mart/scripts.pory"
	waitmessage
# 13 "data/maps/TownLab_Mart/scripts.pory"
	pokemart TownLab_Mart_Stock
# 14 "data/maps/TownLab_Mart/scripts.pory"
	msgbox gText_PleaseComeAgain, MSGBOX_DEFAULT
# 15 "data/maps/TownLab_Mart/scripts.pory"
	release
	end


	.align 2
# 19 "data/maps/TownLab_Mart/scripts.pory"
TownLab_Mart_Stock:
# 20 "data/maps/TownLab_Mart/scripts.pory"
	.2byte ITEM_POKE_BALL
# 21 "data/maps/TownLab_Mart/scripts.pory"
	.2byte ITEM_POTION
# 22 "data/maps/TownLab_Mart/scripts.pory"
	.2byte ITEM_ANTIDOTE
# 23 "data/maps/TownLab_Mart/scripts.pory"
	.2byte ITEM_PARALYZE_HEAL
# 24 "data/maps/TownLab_Mart/scripts.pory"
	.2byte ITEM_AWAKENING
	.2byte ITEM_NONE
