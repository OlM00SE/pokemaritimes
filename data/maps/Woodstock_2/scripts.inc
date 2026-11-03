Woodstock_2_MapScripts::
	.byte 0


Woodstock_2_EventScript_TownSign::
# 8 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_TownSign_Text_0, MSGBOX_SIGN
	end


Woodstock_2_EventScript_StationSign::
# 13 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_StationSign_Text_0, MSGBOX_SIGN
	end


Woodstock_2_EventScript_GardenSign::
# 18 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_GardenSign_Text_0, MSGBOX_SIGN
	end


Woodstock_2_EventScript_Gardener::
# 23 "data/maps/Woodstock_2/scripts.pory"
	lock
# 24 "data/maps/Woodstock_2/scripts.pory"
	faceplayer
# 25 "data/maps/Woodstock_2/scripts.pory"
	goto_if_set FLAG_WOODSTOCK_2_GARDENER_GIFT, Woodstock_2_EventScript_Gardener_2
# 28 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_1
# 29 "data/maps/Woodstock_2/scripts.pory"
	giveitem ITEM_ORAN_BERRY
# 30 "data/maps/Woodstock_2/scripts.pory"
	compare VAR_RESULT, FALSE
	goto_if_eq Woodstock_2_EventScript_Gardener_6
Woodstock_2_EventScript_Gardener_5:
# 33 "data/maps/Woodstock_2/scripts.pory"
	setflag FLAG_WOODSTOCK_2_GARDENER_GIFT
# 34 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_0
Woodstock_2_EventScript_Gardener_1:
# 36 "data/maps/Woodstock_2/scripts.pory"
	release
	end

Woodstock_2_EventScript_Gardener_2:
# 26 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_0
	goto Woodstock_2_EventScript_Gardener_1

Woodstock_2_EventScript_Gardener_6:
# 31 "data/maps/Woodstock_2/scripts.pory"
	goto Common_EventScript_ShowBagIsFull
	goto Woodstock_2_EventScript_Gardener_5


Woodstock_2_EventScript_StationWorker::
# 41 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_StationWorker_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Kid::
# 46 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Kid_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Angler::
# 51 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Angler_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Walker::
# 56 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Walker_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_TownSign_Text_0:
# 8 "data/maps/Woodstock_2/scripts.pory"
	.string "WOODSTOCK\nThe river town in the woods.$"

Woodstock_2_EventScript_StationSign_Text_0:
# 13 "data/maps/Woodstock_2/scripts.pory"
	.string "WOODSTOCK WILDLIFE STATION\nPokémon field research$"

Woodstock_2_EventScript_GardenSign_Text_0:
# 18 "data/maps/Woodstock_2/scripts.pory"
	.string "COMMUNITY GARDEN\nPlease share the harvest!$"

Woodstock_2_EventScript_Gardener_Text_0:
# 26 "data/maps/Woodstock_2/scripts.pory"
	.string "A Pokémon holding an Oran Berry will eat\n"
	.string "it when it gets weak in battle.$"

Woodstock_2_EventScript_Gardener_Text_1:
# 28 "data/maps/Woodstock_2/scripts.pory"
	.string "The berry bushes came in so well this\n"
	.string "year, there's plenty to go around.\p"
	.string "Here, take one for your Pokémon!$"

Woodstock_2_EventScript_StationWorker_Text_0:
# 41 "data/maps/Woodstock_2/scripts.pory"
	.string "We count the Pokémon living along the\n"
	.string "river and in the woods around town.\p"
	.string "Our field researchers go as far as the\n"
	.string "forestry village up Route 201.$"

Woodstock_2_EventScript_Kid_Text_0:
# 46 "data/maps/Woodstock_2/scripts.pory"
	.string "I'm going to be a Pokémon researcher\n"
	.string "when I grow up!\p"
	.string "I already know every Pokémon in the\n"
	.string "garden.$"

Woodstock_2_EventScript_Angler_Text_0:
# 51 "data/maps/Woodstock_2/scripts.pory"
	.string "Nothing's biting today. You need a\n"
	.string "fishing rod to catch Pokémon in the\l"
	.string "water.\p"
	.string "The big ones stay out in the river.$"

Woodstock_2_EventScript_Walker_Text_0:
# 56 "data/maps/Woodstock_2/scripts.pory"
	.string "This road heads south along the river\n"
	.string "to the city.\p"
	.string "It's a long walk, but it's pretty this\n"
	.string "time of year.$"
