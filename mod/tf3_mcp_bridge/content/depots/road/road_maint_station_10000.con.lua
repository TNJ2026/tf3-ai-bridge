local function makeConstructionTemplates()
	local templates = {}

	local function addTemplate(from, to)
		local yearCoefficient = from >= 1980 and 9 or (from >= 1940 and 3 or 1)
		table.insert(templates, {
			type = "DYNAMIC",
			configureLayerScript = {
				fileName = "::/gui/construction/construction_desc_layers.script@configureDefaultLayerFn",
				params = {
					heightmapContours = true,
				}
			},
			configureHudIconsScript = {
				fileName = "::/gui/construction/construction_desc_hud_icons.script@configureDepotHudIconsFn",
				params = {
					depotType = "ROAD",
				}
			},
			availability = {
				yearFrom = from,
				yearTo = to
			},
			description = {
				name = "道路维护设施（6000米）",
				description = "维护半径6000米，同时维护30辆道路车辆。",
				icon = "::/depots/road/road_maint_station.tga",
				previewIcon = "::/depots/road/road_maint_station_preview.tga",
				attributes = {
					noise =  { 20, -1 },
					pollution = { 40, -1 },
					maintenanceCost = { 10000 * yearCoefficient, -1 },
					cost = { 60000 * yearCoefficient, -1 },
				}
			},
			data = {
				params = {},
			},
			menuCategory = {
				categories = {
					{
						category = "road_buildings",
						order = 8000,
					},
				},
			},
		})
	end
	addTemplate(1900, 1940)
	addTemplate(1940, 1980)
	addTemplate(1980, 0)

	return templates
end

function data()

return {
	configureLayerScript = {
		fileName = "::/gui/construction/construction_desc_layers.script@configureDefaultLayerFn",
		params = {
			heightmapContours = true,
		}
	},
	description = {
		name = "道路维护设施（6000米）",
		description = "维护半径6000米，同时维护30辆道路车辆。",
		icon = "::/depots/road/road_maint_station.tga",
		previewIcon = "::/depots/road/road_maint_station_preview.tga",
		attributes = {
			noise =  { 20, -1 },
			pollution = { 40, -1 },
			maintenanceCost = { 20000, -1 },
			cost = { 120000, -1 },
		}
	},
	namePrefix = _("{townName} Maintenance Building"),
	subConstructionNamePrefix = "{constructionName}",
	availability = {
	},
	order = 3000,
	updateScript = {
		fileName = "road_maint_station_10000.script@updateFn",
		params = {
			radius = 6000,
		}
	},
	createTemplateScript = {
		fileName = "::/depots/road/road_maint_station.script@createTemplateFn",
		params = {
		}
	},
	soundConfig = {
		soundSet = {
			name = "::/depots/road/sound/truckdepot.snd",
		},
		effects = {
			select =  {
				"::/depots/road/sound/selected_road_maint_station.wav",
			},
		},
		builderAudioRes = "::/gui/construction/sound/buildoze_construction_small.builder_audio",
	},
	constructionTemplates = makeConstructionTemplates(),
}

end
