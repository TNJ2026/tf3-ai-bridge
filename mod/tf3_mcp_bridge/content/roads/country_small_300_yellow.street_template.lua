function data()
return {
		availability = {
			yearFrom = 1940,
			yearTo = 0,
			notificationGroup = "countryNew",
			notificationSortKey = 10,
			notifyWhenAvailable = false,
		},
		cost = 180,
		country = true,
		defaultWithCrosswalk = false,
		description = {
			description = _("STREET_COUNTRY_NEW_SMALL_DESC"),
			icon = "::/infrastructure/street/country/country_new_small.tga",
			name = "小型乡村公路（黄色 · 300 km/h）",
			previewIcon = "::/infrastructure/street/country/country_new_small_preview.tga",
		},
		emissions = {
			noise = 0,
			pollution = 0,
			pollutionRadius = 0,
			radius = 0,
		},
		fillGroundTex = "::/infrastructure/street/shared/street_fill.gtex",
		laneConfigs = {
			{
				forward = false,
				height = 0,
				offset = -1,
				speed = 22.22,
				transportModes = { "PERSON", "CARGO", },
				width = 2,
			},
			{
				forward = false,
				height = 0,
				offset = -0.5,
				speed = 300 / 3.6,
				transportModes = { "CAR", "BUS", "TRUCK", },
				width = 5,
			},
			{
				forward = true,
				height = 0,
				offset = 0.5,
				speed = 300 / 3.6,
				transportModes = { "CAR", "BUS", "TRUCK", },
				width = 5,
			},
			{
				forward = true,
				height = 0,
				offset = 1,
				speed = 22.22,
				transportModes = { "PERSON", "CARGO", },
				width = 2,
			},
		},
		maintenanceCost = 30,
		menuCategory = {
			categories = {
				{
					category = "roads_country",
					filterCategories = { },
					order = 440,
				},
			},
		},
		modifiers = {
			maxSpeedModifier = 0,
			noiseModifier = 0,
			pollutionModifier = 0,
		},
		pedestrianWalkPenalty = true,
		priority = 200,
		roadType = "STREET",
		sidewalkFillGroundTex = "::/infrastructure/shared/none.gtex",
		simBuildable = true,
		streetStyle = "tnj_tf3_ai_bridge::/roads/country_small_yellow.street",
		builderAudioRes = "::/gui/construction/sound/buildoze_street.builder_audio",
	}
end
