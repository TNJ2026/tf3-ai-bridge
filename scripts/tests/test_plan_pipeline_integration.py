"""Run the real offline entry and its child stages without local export artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf8')
    return path


def test_explicit_templates_and_missing_raw_supply_through_real_pipeline(tmp_path):
    city = {'heliport': (150, 130), 'warehouse': (150, -130),
            'truck': (0, 70), 'bus': (0, -70), 'road_depot': (-130, 70)}
    production = {'helipad': (100, 70), 'helipad2': (150, 70),
                  'warehouse': (150, -70), 'truck': (0, 70)}
    template_paths = {}
    for kind, positions in [('city', city), ('production', production)]:
        template = dict(
            facilities=[dict(role=r, resource=r, localPosition=dict(x=x, y=y),
                             relativeRotation=0, params=dict(modules={}))
                        for r, (x, y) in positions.items()],
            roads=[dict(node0=10, node1=11, position0=dict(x=-80, y=0),
                        position1=dict(x=220, y=0), roadTemplate='country/country_new_small')])
        template_paths[kind] = write(tmp_path/(kind+'.json'), template)
    grid = dict(x=-2000, y=-2000, nx=81, ny=81, spacing=50,
                heights=[0]*6561, water=[False]*6561)
    industries = [dict(id=2, fileName='industry/livestock_farm/farm.con', position=dict(x=-200, y=60)),
                  dict(id=3, fileName='industry/quarry/quarry.con', position=dict(x=-100, y=60))]
    state = dict(player=1, date=dict(year=1960))
    snapshot = dict(
        grid=grid, state=state, bounds=dict(min=dict(x=-2000, y=-2000), max=dict(x=2000, y=2000)),
        map=dict(towns=[dict(id=1, name='Test', position=dict(x=0, y=0))], industries=industries),
        obstacles=[dict(kind='BASE_EDGE', entity=5, node0=10, node1=11,
                        position0=dict(x=-300, y=0, z=0), position1=dict(x=850, y=0, z=0),
                        tangent0=dict(x=1150, y=0, z=0), tangent1=dict(x=1150, y=0, z=0),
                        min=dict(x=-300, y=-3), max=dict(x=850, y=3)),
                   dict(kind='TOWN_BUILDING', entity=4, min=dict(x=-20, y=20), max=dict(x=20, y=40))])
    details = dict(
        state=state, frozenNodes=[],
        buildings=[dict(id=4, town=1, demands={'7': 5, '24': 3})],
        industries=[dict(id=i['id'], resource=i['fileName'], position=i['position'],
                         construction=100+i['id'], stations=[]) for i in industries],
        cargos=[dict(id=c, name=str(c), timeToDeliverInSeconds=1000)
                for c in (1, 3, 7, 12, 13, 15, 18, 20, 24)])
    # Livestock has no grain supplier. The independent quarry flow must still survive.
    capacity = dict(industries=[dict(id=2, inputs={'1': 10}, outputs={'7': 10}),
                               dict(id=3, inputs={}, outputs={'24': 10})])
    inputs = {name: write(tmp_path/(name+'.json'), value)
              for name, value in [('snapshot', snapshot), ('details', details), ('capacity', capacity)]}
    env = dict(os.environ, PYTHONPATH=str(ROOT/'server/src'))

    def run(name, baseline=None):
        output = tmp_path/name
        command = [sys.executable, str(ROOT/'scripts/plan_pipeline.py'), '--output', str(output)]
        for key, path in inputs.items():
            command += ['--'+key, str(path)]
        for kind, path in template_paths.items():
            command += ['--'+kind+'-template', str(path)]
        if baseline:
            command += ['--baseline', str(baseline)]
        result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout+result.stderr+'\n'+''.join(p.read_text('utf8') for p in output.glob('*.log'))
        return output, json.loads((output/'pipeline.json').read_text('utf8'))

    first, report = run('first')
    assert report['status'] == 'complete'
    plan = json.loads((first/'network_plan.json').read_text('utf8'))
    assert next(r for r in plan['raw_supply'] if r['cargo'] == 1)['gap'] == 10
    livestock = next(r for r in plan['supply'] if r['cargo'] == 7)
    assert (livestock['available'], livestock['allocated'], livestock['gap']) == (0, 0, 5)
    assert any(line['cargos'].get('24') == 3 for line in plan['line_specs'])
    assert all('7' not in line['cargos'] for line in plan['line_specs'])
    assert not plan['hubs']
    assert len(plan['collection_quantity_decisions']['service_inventory'])==3
    assert not any(f.get('owner')=='T1' for f in plan['facilities'])
    assert (first/'templates/city.json').exists()
    assert json.loads((first/'readiness.json').read_text('utf8'))['gameCalls'] == 0
    assert 'Test主城' in (first/'DELIVERY.md').read_text('utf8')
    assert '怀化' not in (first/'SUPPLY.md').read_text('utf8')
    assert '已完成' not in (first/'SUPPLY.md').read_text('utf8')
    second, report = run('second', first)
    assert all(s['cacheHit'] for s in report['stages'] if s['stage'] in ('layout', 'network'))
    capacity['industries'][1]['outputs']['1'] = 4
    write(inputs['capacity'], capacity)
    supplied, report = run('partial-supply', second)
    assert next(s for s in report['stages'] if s['stage'] == 'layout')['cacheHit']
    assert not next(s for s in report['stages'] if s['stage'] == 'network')['cacheHit']
    plan = json.loads((supplied/'network_plan.json').read_text('utf8'))
    livestock = next(r for r in plan['supply'] if r['cargo'] == 7)
    assert (livestock['available'], livestock['allocated'], livestock['gap']) == (4, 4, 1)
    assert next(r for r in plan['raw_supply'] if r['cargo'] == 1)['gap'] == 6
    template = json.loads(template_paths['city'].read_text('utf8'))
    template['facilities'][0]['localPosition']['x'] += 10
    write(template_paths['city'], template)
    _, report = run('changed-template', supplied)
    assert not next(s for s in report['stages'] if s['stage'] == 'layout')['cacheHit']

    # Bundled templates must work from a foreign cwd without any historical exports.
    template_paths.clear()
    bundled, report = run('bundled')
    city = json.loads((bundled/'templates/city.json').read_text('utf8'))
    assert len(city['roads']) == 6
    assert 'road_maintenance' in {f['role'] for f in city['facilities']}
    assert city['placementMode'] == 'joint'
    assert all(r['roadTemplate']=='country/country_new_medium' for r in city['roads'])
    assert city['rolePortNodes']['truck'] != city['rolePortNodes']['road_depot']
    assert json.loads((bundled/'report_plan.json').read_text('utf8'))['snapshot']['map']['towns'][0]['name'] == 'Test'

    # Two allocated fishing grounds share one six-role port through every stage.
    fish=[dict(id=i,fileName='industry/fishing_grounds/fish.con',position=dict(x=x,y=1300))for i,x in [(6,0),(8,600)]]
    snapshot['map']['industries']=fish
    snapshot['grid']['water']=[(-2000+y*50)>=700 for y in range(81)for x in range(81)]
    details['industries']=[dict(id=i['id'],resource=i['fileName'],position=i['position'],construction=100+i['id'],stations=[])for i in fish]
    details['buildings'][0]['demands']={'6':80}
    details['cargos'].append(dict(id=6,name='fish',timeToDeliverInSeconds=1000))
    capacity['industries']=[dict(id=i['id'],inputs={},outputs={'6':40})for i in fish]
    for key,value in [('snapshot',snapshot),('details',details),('capacity',capacity)]:write(inputs[key],value)
    fishing,_=run('paired-fishing')
    plan=json.loads((fishing/'network_plan.json').read_text('utf8'))
    assert len(plan['ports'])==1
    port=plan['ports'][0]
    assert port['service_industries']==[6,8] and port['annual_forecast']==80
    assert set(plan['shared_fishing_ports'])=={'6','8'}
    ships=[l for l in plan['line_specs']if l['mode']=='SMALL_SHIP']
    planes=[l for l in plan['line_specs']if l['mode']=='HELICOPTER']
    assert len(ships)==2 and sum(l['cargos']['6']for l in ships)==80
    assert len(planes)==2 and sum(l['cargos']['6']for l in planes)==80
    assert len({l['source']for l in planes})==2
    assert all(l['purchase_base']==port['purchase_base']for l in ships)
    manifest=json.loads((fishing/'execution_manifest.json').read_text('utf8'))
    jobs=manifest['jobs']
    assert len([j for j in jobs if j.get('collection_owner')==port['id']])==6
    for ship in ships:
        job=next(j for j in jobs if j['id']==ship['id'])
        assert {port['purchase_base'],port['maintenance_base'],port['warehouse']}<=set(job['depends_on'])
    queue=json.loads((fishing/'review_queue.json').read_text('utf8'))
    assert queue['fishPorts'][0]['serviceIndustries']==[6,8]
    assert '6,8' in (fishing/'COLLECTIONS.md').read_text('utf8')
