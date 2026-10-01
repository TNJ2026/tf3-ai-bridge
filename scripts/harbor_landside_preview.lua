local out={station=B.commands.get_entity({id=106244}),stations=B.commands.list_stations({})}
out.road=B.commands.build_road({start={node=70826},['end']={x=1915,y=-2082},street_type='town/town_old_small',max_segment_length=50,preview=true})
out.truckStation=B.commands.build_station({x=1870,y=-1940,rotation=0,cargo=true,size=1,connect=false,preview=true,name='牡丹江南岸码头接驳站'})
return B.json.encode(out)
