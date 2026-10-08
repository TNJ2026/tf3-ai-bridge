return B.json.encode({game=B.commands.get_game_state(),vehicles=B.commands.list_vehicles({}),lines=B.commands.list_lines({})})
