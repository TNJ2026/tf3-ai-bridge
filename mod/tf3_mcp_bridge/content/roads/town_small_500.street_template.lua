function data()
return {
		availability = {
			yearFrom = 1940,
			yearTo = 0,
			notificationGroup = "townNew",
			notificationSortKey = 20,
			notifyWhenAvailable = false,
		},
		borderGroundTex = "::/infrastructure/street/shared/town_street_border.gtex",
		cost = 180,
		description = {
			description = _("STREET_TOWN_NEW_SMALL_DESC"),
			icon = "::/infrastructure/street/town/town_new_small.tga",
			name = "小型街道（500 km/h）",
			previewIcon = "::/infrastructure/street/town/town_new_small_preview.tga",
		},
		emissions = {
			noise = 0,
			pollution = 0,
			pollutionRadius = 0,
			radius = 0,
		},
		fillGroundTex = "::/infrastructure/street/shared/town_street_fill.gtex",
		laneConfigs = {
			{
				forward = false,
				height = 0.15,
				offset = 0.15,
				speed = 13.89,
				transportModes = { "PERSON", "CARGO", },
				width = 3,
			},
			{
				forward = false,
				height = 0,
				offset = -0.5,
				speed = 500 / 3.6,
				transportModes = { "CAR", "BUS", "TRUCK", },
				width = 5,
			},
			{
				forward = true,
				height = 0,
				offset = 0.5,
				speed = 500 / 3.6,
				transportModes = { "CAR", "BUS", "TRUCK", },
				width = 5,
			},
			{
				forward = true,
				height = 0.15,
				offset = -0.15,
				speed = 13.89,
				transportModes = { "PERSON", "CARGO", },
				width = 3,
			},
		},
		maintenanceCost = 30,
		menuCategory = {
			categories = {
				{
					category = "roads_small",
					filterCategories = { },
					order = 20,
				},
			},
		},
		modifiers = {
			maxSpeedModifier = 0,
			noiseModifier = 0,
			pollutionModifier = 0,
		},
		priority = 610,
		roadType = "STREET",
		sidewalkFillGroundTex = "::/infrastructure/street/shared/street_sidewalk_fill.gtex",
		simBuildable = true,
		streetStyle = "tnj_tf3_ai_bridge::/roads/town_small_500_paving.street",
		builderAudioRes = "::/gui/construction/sound/buildoze_street.builder_audio",
	}
end
