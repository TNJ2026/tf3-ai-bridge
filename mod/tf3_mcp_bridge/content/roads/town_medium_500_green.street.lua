function data()
return {
	roadType = "STREET",
	materials = {
		streetPaving = {
			name = "tnj_tf3_ai_bridge::/roads/mat/green_paving.mtl",
			size = { 6.0, 6.0 }
		},
		streetBorder = {
			name = "::/infrastructure/street/town/mat/new_town_border.mtl",
			size = { 24.0, 3.0 }
		},
		streetBorder2 = {
			name = "::/infrastructure/street/shared/mat/new_shared_border.mtl",
			size = { 24.0, 3.0 }
		},
		streetLane = {
			name = "tnj_tf3_ai_bridge::/roads/mat/green_lane.mtl",
			size = { 4.0, 5.0 }
		},
		streetArrow = {
			name = "::/infrastructure/street/shared/mat/default_arrows.mtl",
			size = { 9.0, 3.0 }
		},
		streetStripe = {
			name = "::/infrastructure/street/town/mat/new_town_stripe.mtl",
			size = { 24.0, 0.37 }
		},
		streetStripeMedian = {
			name = "::/infrastructure/street/town/mat/new_town_median.mtl",
			size = { 24.0, 0.37 }
		},
		streetBus = {
			name = "::/infrastructure/street/town/mat/new_medium_bus.mtl",
			size = { 12, 2.7 }
		},
		streetTram = {
			name = "::/infrastructure/street/shared/mat/new_tram_paving.mtl",
			size = { 2.0, 2.0 }
		},
		streetTramTrack = {
			name = "::/infrastructure/street/shared/mat/new_tram_track.mtl",
			size = { 2.0, 2.0 }
		},
		crossingLane = {
			name = "tnj_tf3_ai_bridge::/roads/mat/green_lane.mtl",
			size = { 4.0, 4.0 }
		},
		crossingBus = {
			name = ""
		},
		crossingTram = {
			name = "::/infrastructure/street/shared/mat/new_tram_paving.mtl",
			size = { 2.0, 2.0 }
		},
		crossingTramTrack = {
			name = "::/infrastructure/street/shared/mat/new_tram_track.mtl",
			size = { 2.0, 2.0 }
		},
		crossingCrosswalk = {
			name = "::/infrastructure/street/shared/mat/new_crosswalk.mtl",
			size = { 3.0, 2.5 }
		},
		sidewalkPaving = {
			name = "::/infrastructure/street/town/mat/new_medium_sidewalk_prototype.mtl",
			size = { 32.0, 32.0 }
		},
		sidewalkLane = {

		},
		sidewalkBorderInner = {
			name = "::/infrastructure/street/town/mat/new_town_sw_in.mtl",
			size = { 24, 1.5 }
		},
		-- sidewalkBorderOuter = {
			-- name = "::/infrastructure/street/town/mat/new_medium_sidewalk_border_outer.mtl",
			-- size = { 8.0, 0.41602 }
		-- },
		sidewalkCurb = {
			name = "::/infrastructure/street/town/mat/new_town_sw_curb.mtl",
			size = { 24, .35 }
		},
		-- sidewalkWall = {
			-- name = "::/infrastructure/street/town/mat/new_medium_sidewalk_wall.mtl",
			-- size = { 8.0, 0.41602 }
		-- },
		catenary = {
			name = "::/infrastructure/street/shared/mat/tram_cable.mtl"
		},
		junctionBorder = {
			name = "::/infrastructure/street/town/mat/new_town_border.mtl",
			size = { 24.0, 3.0 }
		},
		-- junctionBorder2 = {
		-- 	name = "::/infrastructure/street/shared/mat/new_shared_border.mtl",
		-- 	size = { 24.0, 3.0 }
		-- },
	},
	assets = {
		["street_light"] = {
			name = "::/assets/streets/street_light_eu_c.mdl",
			offset = 8.0,
			distance = 16.0,
			prob = 1.0,
			offsetOrth = 3.0,
			randRot = false,
			oneSideOnly = false,
			alignToElevation = false,
			avoidFaceEdges = false,
			placeOnBridge = true,
		},
		["fireplug"] = {
			name = "::/assets/streets/fireplug_c.mdl",
			offset = 10.0,
			distance = 40.0,
			prob = 0.5,
			offsetOrth = 0.35,
			randRot = false,
			oneSideOnly = false,
			alignToElevation = false,
			avoidFaceEdges = false,
		},
		["trash"] = {
			name = "::/assets/streets/trash_standing_c.mdl",
			offset = 20,
			distance = 50.0,
			prob = 0.5,
			offsetOrth = 0.4,
			randRot = false,
			oneSideOnly = false,
			alignToElevation = false,
			avoidFaceEdges = false,
		},
	},
	catenary = {
		pole = {
			name = "::/assets/streets/tram_pole.mdl",
		},
		poleCrossbar = {
			name = "::/assets/streets/tram_pole_crossbar.mdl",
		},
		poleDoubleCrossbar = {
			name = "::/assets/streets/tram_pole_double_crossbar.mdl",
		},
		isolatorStraight = "::/assets/streets/cable_isolator.mdl",
		isolatorCurve = "::/assets/streets/cable_isolator.mdl",
		junction = "::/assets/streets/cable_junction.mdl"
	},
	categoryList = {
		categories = {
			"withSidewalk",
			"town",
			"new",
		}
	},
	arrowIndices = {
		LEFT = 0,
		STRAIGHT = 1,
		RIGHT = 2,
		LEFT_STRAIGHT = 3,
		RIGHT_STRAIGHT = 4,
		LEFT_RIGHT = 5,
		LEFT_RIGHT_STRAIGHT = 6
	},
	priority = 620,
}
end
