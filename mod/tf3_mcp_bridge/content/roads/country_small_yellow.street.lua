function data()
return {
	roadType = "STREET",
	categoryList = {
		categories = {
			"country",
			"new",
		}
	},
	materials = {
		streetPaving = {
			name = "tnj_tf3_ai_bridge::/roads/mat/country_yellow_paving.mtl",
			size = { 8.0, 8.0 }
		},
		streetBorder = {
			name = "::/infrastructure/street/country/mat/new_country_border.mtl",
			size = { 24, 3.0}
		},
		crossingBorder = {
			name = "::/infrastructure/street/country/mat/new_country_border.mtl",
			size = { 12, 3.0 }
		},
		junctionBorder = {
			name = "::/infrastructure/street/country/mat/new_country_border.mtl",
			size = { 12, 3.0 }
		},
		streetLane = {
			name = "tnj_tf3_ai_bridge::/roads/mat/country_yellow_lane.mtl",
			size = { 3.0, 3.0 }
		},
		streetArrow = {
			name = "::/infrastructure/street/shared/mat/default_arrows.mtl",
			size = { 9.0, 3.0 }
		},
		streetStripe = {
			name = "::/infrastructure/street/country/mat/new_country_stripe.mtl",
			size = { 24.0, .37 }
		},
		junctionStripe = {
			name = "::/infrastructure/street/country/mat/new_country_stripe.mtl",
			size = { 24.0, 0.37 }
		},
		streetStripeMedian = {
			name = "::/infrastructure/street/country/mat/new_country_median.mtl",
			size = { 24.0, 0.75 }
		},
		junctionStripeMedian = {
			name = "::/infrastructure/street/country/mat/new_country_median.mtl",
			size = { 24, 0.75 }
		},
		streetTram = {
			name = "::/infrastructure/street/shared/mat/new_tram_paving.mtl",
			size = { 2.0, 2.0 }
		},
		streetTramTrack = {
			name = "::/infrastructure/street/shared/mat/new_tram_track.mtl",
			size = { 2.0, 2.0 }
		},
		streetBus = {
			name = "::/infrastructure/street/town/mat/new_medium_bus.mtl",
			size = { 12, 2.7 }
		},
		crossingLane = {
			name = "tnj_tf3_ai_bridge::/roads/mat/country_yellow_lane.mtl",
			size = { 3.0, 3.0 }
		},
		crossingBus = {
			name = "",
		},
		crossingTram = {
			name = "::/infrastructure/street/shared/mat/new_tram_paving.mtl",
			size = { 2.0, 2.0 }
		},
		crossingTramTrack = {
			name = "::/infrastructure/street/shared/mat/new_tram_track.mtl",
			size = { 2.0, 2.0 }
		},
		sidewalkPaving = {
		},
		sidewalkLane = {
		},
		sidewalkBorderInner = {
		},
		sidewalkBorderOuter = {
		},
		sidewalkCurb = {
		},
		sidewalkWall = {
		}
	},
	assets = {

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
	priority = 800,
}
end
