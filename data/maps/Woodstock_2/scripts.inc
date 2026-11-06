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


Woodstock_2_EventScript_CreekSign::
# 23 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_CreekSign_Text_0, MSGBOX_SIGN
	end


Woodstock_2_EventScript_NorthSign::
# 28 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_NorthSign_Text_0, MSGBOX_SIGN
	end


Woodstock_2_EventScript_Gardener::
# 33 "data/maps/Woodstock_2/scripts.pory"
	lock
# 34 "data/maps/Woodstock_2/scripts.pory"
	faceplayer
# 35 "data/maps/Woodstock_2/scripts.pory"
	goto_if_set FLAG_WOODSTOCK_2_GARDENER_GIFT, Woodstock_2_EventScript_Gardener_2
# 38 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_1
# 39 "data/maps/Woodstock_2/scripts.pory"
	giveitem ITEM_ORAN_BERRY
# 40 "data/maps/Woodstock_2/scripts.pory"
	compare VAR_RESULT, FALSE
	goto_if_eq Woodstock_2_EventScript_Gardener_6
Woodstock_2_EventScript_Gardener_5:
# 43 "data/maps/Woodstock_2/scripts.pory"
	setflag FLAG_WOODSTOCK_2_GARDENER_GIFT
# 44 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_0
Woodstock_2_EventScript_Gardener_1:
# 46 "data/maps/Woodstock_2/scripts.pory"
	release
	end

Woodstock_2_EventScript_Gardener_2:
# 36 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Gardener_Text_0
	goto Woodstock_2_EventScript_Gardener_1

Woodstock_2_EventScript_Gardener_6:
# 41 "data/maps/Woodstock_2/scripts.pory"
	goto Common_EventScript_ShowBagIsFull
	goto Woodstock_2_EventScript_Gardener_5


Woodstock_2_EventScript_StationWorker::
# 51 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_StationWorker_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Kid::
# 56 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Kid_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Angler::
# 61 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Angler_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_Walker::
# 66 "data/maps/Woodstock_2/scripts.pory"
	msgbox Woodstock_2_EventScript_Walker_Text_0, MSGBOX_NPC
	end


Woodstock_2_EventScript_TownSign_Text_0:
# 8 "data/maps/Woodstock_2/scripts.pory"
	.string "WOODSTOCK\nThe town where two rivers meet.$"

Woodstock_2_EventScript_StationSign_Text_0:
# 13 "data/maps/Woodstock_2/scripts.pory"
	.string "WOODSTOCK WILDLIFE STATION\nPokémon field research$"

Woodstock_2_EventScript_GardenSign_Text_0:
# 18 "data/maps/Woodstock_2/scripts.pory"
	.string "COMMUNITY GARDEN\nPlease share the harvest!$"

Woodstock_2_EventScript_CreekSign_Text_0:
# 23 "data/maps/Woodstock_2/scripts.pory"
	.string "MEDUXNEKEAG RIVER\nIt joins the Saint John right here.$"

Woodstock_2_EventScript_NorthSign_Text_0:
# 28 "data/maps/Woodstock_2/scripts.pory"
	.string "NORTH: HARTLAND\nThe trail is closed past here.$"

Woodstock_2_EventScript_Gardener_Text_0:
# 36 "data/maps/Woodstock_2/scripts.pory"
	.string "A Pokémon holding an Oran Berry will eat\n"
	.string "it when it gets weak in battle.$"

Woodstock_2_EventScript_Gardener_Text_1:
# 38 "data/maps/Woodstock_2/scripts.pory"
	.string "The berry bushes came in so well this\n"
	.string "year, there's plenty to go around.\p"
	.string "Here, take one for your Pokémon!$"

Woodstock_2_EventScript_StationWorker_Text_0:
# 51 "data/maps/Woodstock_2/scripts.pory"
	.string "We count the Pokémon living along the\n"
	.string "river and in the woods around town.\p"
	.string "Our field researchers go as far as the\n"
	.string "forestry village up Route 201.$"

Woodstock_2_EventScript_Kid_Text_0:
# 56 "data/maps/Woodstock_2/scripts.pory"
	.string "I'm going to be a Pokémon researcher\n"
	.string "when I grow up!\p"
	.string "I already know every Pokémon in the\n"
	.string "garden.$"

Woodstock_2_EventScript_Angler_Text_0:
# 61 "data/maps/Woodstock_2/scripts.pory"
	.string "Nothing's biting today. You need a\n"
	.string "fishing rod to catch Pokémon in the\l"
	.string "water.\p"
	.string "The big ones stay out in the Saint John.$"

Woodstock_2_EventScript_Walker_Text_0:
# 66 "data/maps/Woodstock_2/scripts.pory"
	.string "This road heads south along the river\n"
	.string "to the city.\p"
	.string "It's a long walk, but it's pretty this\n"
	.string "time of year.$"
