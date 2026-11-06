Woodstock_Mart_MapScripts::
	.byte 0


Woodstock_Mart_EventScript_Clerk::
# 9 "data/maps/Woodstock_Mart/scripts.pory"
	lock
# 10 "data/maps/Woodstock_Mart/scripts.pory"
	faceplayer
# 11 "data/maps/Woodstock_Mart/scripts.pory"
	message gText_HowMayIServeYou
# 12 "data/maps/Woodstock_Mart/scripts.pory"
	waitmessage
# 13 "data/maps/Woodstock_Mart/scripts.pory"
	pokemart Woodstock_Mart_Stock
# 14 "data/maps/Woodstock_Mart/scripts.pory"
	msgbox gText_PleaseComeAgain, MSGBOX_DEFAULT
# 15 "data/maps/Woodstock_Mart/scripts.pory"
	release
	end


	.align 2
# 19 "data/maps/Woodstock_Mart/scripts.pory"
Woodstock_Mart_Stock:
# 20 "data/maps/Woodstock_Mart/scripts.pory"
	.2byte ITEM_POKE_BALL
# 21 "data/maps/Woodstock_Mart/scripts.pory"
	.2byte ITEM_POTION
# 22 "data/maps/Woodstock_Mart/scripts.pory"
	.2byte ITEM_ANTIDOTE
# 23 "data/maps/Woodstock_Mart/scripts.pory"
	.2byte ITEM_PARALYZE_HEAL
# 24 "data/maps/Woodstock_Mart/scripts.pory"
	.2byte ITEM_AWAKENING
	.2byte ITEM_NONE
