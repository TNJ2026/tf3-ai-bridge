"""Bounded receiver project protocol. No host-side per-step construction loop."""
import math
import re

PREVIEWS = {'preview_road', 'preview_network', 'preview_road_graph',
            'build_warehouse', 'build_heliport', 'build_helipad', 'build_airfield',
            'build_water_facility', 'build_headquarters'}
TRANSPORT = {'create_line', 'buy_vehicles', 'assign_vehicles', 'accept_departure', 'preview_line_edit'}
CHECKS = {'get_entity', 'get_facility_config', 'get_facility_access',
          'get_facility_inventory', 'check_road_junction_path', 'check_network_junction_path', 'get_vehicle_motion'}
COMMANDS = {'execute_project', 'resume_project', 'get_project', 'cancel_project'}


def validate_transport(command, args):
    from .ui_log import validate_build_arguments
    if command=='accept_departure' and 'fleets' in args:
        if set(args)!={'fleets','seconds'} or not isinstance(args['fleets'],list) or not 1<=len(args['fleets'])<=8:
            raise ValueError('Departure fleets requires 1-8 line groups')
        for fleet in args['fleets']:
            if not isinstance(fleet,dict) or set(fleet)!={'line','vehicles'}:
                raise ValueError('Departure fleet requires line/vehicles')
            validate_transport(command,dict(fleet,seconds=args['seconds']))
        return
    if command == 'buy_vehicles':
        if set(args) != {'depot','model','count','mode'} or type(args['count']) is not int or not 1 <= args['count'] <= 16:
            raise ValueError('Project purchase requires depot/model/count (1-16)/mode')
        validate_build_arguments('buy_vehicles', {k:v for k,v in dict(args,count=1).items() if k!='mode'})
        if args['mode'] not in {'BUS','TRUCK','TRAM','ELECTRIC_TRAM','TRAIN','ELECTRIC_TRAIN','SMALL_SHIP','SHIP','SMALL_AIRCRAFT','AIRCRAFT','HELICOPTER'}:
            raise ValueError('Explicit native transport mode required')
    elif command in {'assign_vehicles','accept_departure'}:
        fields={'vehicles','line','stop_index'} if command=='assign_vehicles' else {'vehicles','line','seconds'}
        if set(args)!=fields or not isinstance(args['vehicles'],list) or not 1<=len(args['vehicles'])<=16:
            raise ValueError('Project fleet requires 1-16 explicit vehicles')
        for vehicle in args['vehicles']:
            validate_build_arguments('assign_vehicles',dict(vehicles=[vehicle],line=args['line'],stop_index=args.get('stop_index',0)))
        if command=='accept_departure' and (type(args['seconds']) is not int or not 1<=args['seconds']<=120):
            raise ValueError('Departure observation requires 1-120 seconds')
    else:
        validate_build_arguments(command,args)


def validate_project(command, args):
    from .ui_log import validate_build_arguments, validate_save_arguments
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    def money(v):
        return type(v) in (int, float) and math.isfinite(v) and 0 <= v < 1e15
    def template(v, known, depth=0):
        require(depth <= 12, 'Project nesting too deep')
        if isinstance(v, dict):
            if '$ref' in v:
                path = v['$ref']
                require(set(v) == {'$ref'} and isinstance(path, str) and
                        re.fullmatch(r'[a-z][a-z0-9_]{0,31}\.commit(?:\.[A-Za-z0-9_]+)+', path)
                        and path.split('.')[0] in known, 'Invalid/forward project reference')
                return 0  # References are numeric entity/node IDs; validate again after resolution.
            return {k: template(x, known, depth+1) for k,x in v.items()}
        if isinstance(v, list):
            return [template(x, known, depth+1) for x in v]
        return v
    require(isinstance(args, dict), 'Project arguments must be an object')
    fields = {'project_id'}
    if command in ('execute_project', 'resume_project'):
        fields.add('backup_save')
    if command == 'execute_project':
        fields |= {'steps', 'cash_floor', 'reserved_cash'}
    if command=='execute_project' and 'allow_no_costs' in args:
        fields.add('allow_no_costs')
        require(type(args['allow_no_costs']) is bool,'allow_no_costs must be boolean')
    require(set(args) == fields, 'Unexpected/missing project fields')
    require(isinstance(args['project_id'], str) and re.fullmatch('[0-9a-f]{32}', args['project_id']), 'project_id must be 32 hex characters')
    if 'backup_save' in args:
        validate_save_arguments('save_game', {'slot':args['backup_save']})
    if command != 'execute_project':
        return args
    require(money(args['cash_floor']) and args['cash_floor'] >= 5000000 and money(args['reserved_cash']), 'Invalid project cash floor/reserve')
    steps = args['steps']
    require(isinstance(steps, list) and 1 <= len(steps) <= 8, 'Project needs 1-8 steps')
    known = set()
    for index,step in enumerate(steps):
        require(isinstance(step, dict) and set(step) == {'id','preview','arguments','max_cost','checks'}, 'Invalid project step')
        sid = step['id']
        require(isinstance(sid,str) and re.fullmatch('[a-z][a-z0-9_]{0,31}',sid) and sid not in known, 'Invalid/duplicate step id')
        require(step['preview'] in PREVIEWS | TRANSPORT and money(step['max_cost']), 'Unsupported preview or invalid budget')
        require(isinstance(step['arguments'],dict), 'Step arguments must be an object')
        resolved=template(step['arguments'],known)
        if step['preview'] in TRANSPORT:
            validate_transport(step['preview'],resolved)
            if step['preview']!='buy_vehicles':require(step['max_cost']==0,'Non-purchase transport step cost must be zero')
        else:
            validate_build_arguments(step['preview'],resolved)
        if step['preview']=='accept_departure':require(index==len(steps)-1,'Departure must be the last step')
        known.add(sid)
        checks=step['checks']
        require(isinstance(checks,list) and (0 if step['preview']=='accept_departure' else 1)<=len(checks)<=4, 'Each step needs independent acceptance checks')
        if step['preview']=='accept_departure':require(not checks,'Departure uses built-in live acceptance')
        for check in checks:
            require(isinstance(check,dict) and set(check)=={'command','arguments','expect'}, 'Invalid acceptance check')
            require(check['command'] in CHECKS, 'Acceptance command not allowed')
            validate_build_arguments(check['command'],template(check['arguments'],known))
            require(isinstance(check['expect'],dict) and 1<=len(check['expect'])<=8, 'Expected fields required')
            for path,expected in check['expect'].items():
                require(isinstance(path,str) and re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*',path), 'Invalid result field path')
                value=template(expected,known)
                require(type(value) in (str,int,float,bool) and (not isinstance(value,str) or len(value)<=256), 'Expected scalar required')
                require(type(value) not in (int,float) or math.isfinite(value), 'Nonfinite expectation')
    return args
