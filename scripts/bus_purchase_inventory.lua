return B.json.encode({models=B.commands.list_vehicle_models({carrier='ROAD',limit=300}),depots=B.commands.list_depots({}),lines=B.commands.list_lines({})})
