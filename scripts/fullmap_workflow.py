"""Offline preflight, incremental road preparation and delivery from explicit inputs.

Never imports the game bridge, never reuses native previews and never edits inputs.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from fullmap_prepare import RoadSurvey, execution_order, shortlist
from fullmap_identity import facility_id, unique_ids
from fullmap_hub_sets import compile_hub_sets
from tf3_mcp.planning_geometry import facility_polygon, intersects, polygon

VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode('utf8')).hexdigest()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    try:
        temporary.write_text(text, encoding='utf8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


class Timing:
    def __init__(self):
        self.started = time.perf_counter()
        self.rows = []

    @contextmanager
    def stage(self, name):
        started = time.perf_counter()
        success = False
        try:
            yield
            success = True
        finally:
            self.rows.append(dict(stage=name, seconds=time.perf_counter()-started,
                                  success=success))

    def result(self):
        return dict(wall_seconds=time.perf_counter()-self.started, stages=self.rows,
                    scope='offline invocation only; excludes prospecting and earlier human/agent work')


def map_signature(rows, town=False):
    return sorted((r['name'] if town else r.get('resource', r.get('fileName')),
                   round(r['position']['x'], 2), round(r['position']['y'], 2)) for r in rows)


def check_map(plan, snapshot, manifest):
    missing = []
    if plan['session']['player'] != snapshot['state']['player']:
        raise ValueError('plan/snapshot player mismatch')
    for key, snapkey, town in [('cities', 'towns', True), ('industries', 'industries', False)]:
        if map_signature(plan[key], town) != map_signature(snapshot['map'][snapkey], town):
            raise ValueError('plan/snapshot map mismatch: '+key)
    session = manifest.get('session', {})
    if session.get('player') != plan['session']['player']:
        raise ValueError('manifest player mismatch')
    for key, town in [('towns', True), ('industries', False)]:
        if key not in session:
            missing.append('manifest.session.'+key)
        elif map_signature(session[key], town) != map_signature(snapshot['map'][key], town):
            raise ValueError('manifest map mismatch: '+key)
    return missing


def structure(plan, manifest):
    facilities = plan.get('facilities', [])+plan.get('ports', [])
    sections = [('facility', facilities), ('road', plan.get('roads', [])),
                ('stop', plan.get('city_stops', plan.get('stops', []))), ('line', plan.get('line_specs', []))]
    unique_ids([row for _,rows in sections for row in rows])
    ids = set()
    for label, rows in sections:
        for row in rows:
            name = row.get('id')
            if not isinstance(name, str) or not name or name in ids:
                raise ValueError('missing/duplicate planning ID: '+str(name))
            ids.add(name)
            for k in ('position',):
                if k in row and not all(math.isfinite(float(row[k][a])) for a in ('x', 'y')):
                    raise ValueError('nonfinite position: '+name)
    facility_ids = {f['id'] for f in facilities}
    for road in plan.get('roads', []):
        if road.get('to_facility') is not None and road['to_facility'] not in facility_ids:
            raise ValueError('unknown road facility: '+road['id'])
    for hub in plan.get('hubs', []):
        if set(hub['facilities'].values())-facility_ids:
            raise ValueError('unknown hub facility: '+str(hub.get('owner')))
    for port in plan.get('ports', []):
        for key in ('warehouse', 'truck'):
            if port.get(key) not in facility_ids:
                raise ValueError('unknown port transfer facility: '+port['id'])
    planned = {row['id']:row for _,rows in sections for row in rows}
    represented = {j['id'] for j in manifest['jobs'] if j.get('stage') in ('facility','road','street_stop','line')}
    if represented != set(planned):
        raise ValueError('manifest coverage differs from plan: '+str(sorted(represented ^ set(planned))))
    for job in manifest['jobs']:
        stage = job.get('stage')
        if stage in ('facility','road','street_stop','line'):
            row = planned.get(job['id'])
            if row is None:
                raise ValueError('manifest object absent from plan: '+job['id'])
            if stage != 'facility' and job.get('spec') != row:
                raise ValueError('stale manifest spec: '+job['id'])
            if stage == 'facility' and any(job.get(k) != row.get(k) for k in ('position','rotation')):
                raise ValueError('stale manifest facility pose: '+job['id'])
            # Bridge JSON represents an empty Lua table as [] in older snapshots.
            if stage == 'facility' and any((job.get('args') or {}).get(k) != v for k,v in (row.get('args') or {}).items()):
                raise ValueError('stale manifest facility args: '+job['id'])
    # Validation of dependency references and cycles happens before any costly work.
    return execution_order(manifest['jobs'])


def geometry(plan, snapshot):
    rows = plan.get('facilities', [])+plan.get('ports', [])
    shaped = [r for r in rows if all(k in r for k in ('position', 'footprint', 'reserved'))]
    current = {r['id']: facility_polygon(r, 'footprint') for r in shaped}
    reserved = {r['id']: facility_polygon(r, 'reserved') for r in shaped}
    collisions, expansion = [], []
    for i, a in enumerate(shaped):
        for b in shaped[i+1:]:
            if intersects(current[a['id']], current[b['id']]):
                collisions.append([a['id'], b['id']])
            if intersects(reserved[a['id']], reserved[b['id']]):
                expansion.append([a['id'], b['id']])
    obstacles = [(o['entity'], polygon(o)) for o in snapshot['obstacles']
                 if o.get('kind') in ('CONSTRUCTION', 'TOWN_BUILDING')]
    existing = {r['id']: [entity for entity, poly in obstacles
                         if intersects(reserved[r['id']], poly)] for r in shaped}
    return dict(footprint_conflicts=collisions, reservation_conflicts=expansion,
                upgrade_existing_conflicts={k:v for k,v in existing.items() if v},
                missing_geometry=[r['id'] for r in rows if r not in shaped],
                native_verified=False)


def job_changes(manifest, baseline, snapshot_digest):
    jobs = {j['id']: j for j in manifest['jobs']}
    fingerprints = {k:digest(v) for k,v in jobs.items()}
    previous = (baseline or {}).get('job_fingerprints', {})
    same = (baseline or {}).get('snapshot_digest') == snapshot_digest
    changed = {k for k,v in fingerprints.items() if not same or previous.get(k) != v}
    removed = set(previous)-set(jobs)
    affected = set(changed)
    # Change propagation uses the explicit graph, not guessed numeric IDs.
    while True:
        extra = {k for k,v in jobs.items() if set(v.get('depends_on', [])) & affected}
        if extra <= affected:
            break
        affected |= extra
    return dict(changed=sorted(changed), affected=sorted(affected), removed=sorted(removed),
                unchanged=sorted(set(jobs)-affected), job_fingerprints=fingerprints,
                snapshot_digest=snapshot_digest, native_preview_reuse=False,
                note='Only an offline recomputation scope. Always resolve current entities and preview before commit.')


def workflow(plan, snapshot, manifest, baseline=None, timer=None):
    timer = timer or Timing()
    with timer.stage('input_identity_and_dependencies'):
        missing_identity = check_map(plan, snapshot, manifest)
        batches = structure(plan, manifest)
        sd = digest(snapshot)
    with timer.stage('rotated_footprints_and_upgrade_space'):
        layout = geometry(plan, snapshot)
    with timer.stage('road_candidates'):
        survey = RoadSurvey(snapshot)
        prior = (baseline or {}).get('road_cache', {})
        same = ((baseline or {}).get('snapshot_digest') == sd and
                (baseline or {}).get('algorithm') == VERSION)
        cache, roads, hits = {}, [], 0
        for road in plan.get('roads', []):
            key = digest(road)
            old = prior.get(road['id'], {}) if same else {}
            if old.get('key') == key:
                result = old['result']; hits += 1
            else:
                result = shortlist(survey, road)
            roads.append(result)
            cache[road['id']] = dict(key=key, result=result)
    with timer.stage('incremental_scope'):
        changes = job_changes(manifest, baseline, sd)
    with timer.stage('hub_sets_and_review_queue'):
        hub_sets = compile_hub_sets(plan, roads, layout)
    return dict(schema=1, algorithm=VERSION, mode='offline_planning_preflight',
                missing_manifest_identity=missing_identity,
                construction_authorized=False, native_preview_required=True,
                snapshot_digest=sd, road_cache=cache, job_fingerprints=changes['job_fingerprints'],
                changes=changes, geometry=layout, roads=roads, batches=batches, hub_sets=hub_sets,
                counters=dict(facilities=len(plan.get('facilities', []))+len(plan.get('ports', [])),
                              roads=len(roads), jobs=len(manifest['jobs']),
                              road_cache_hits=hits, road_recomputed=len(roads)-hits),
                requires_attention=bool(missing_identity or layout['footprint_conflicts'] or layout['reservation_conflicts']
                    or layout['missing_geometry'] or any(not r['candidates'] for r in roads)
                    or any(g['issues'] for g in hub_sets)),
                limitations=['Read-only coarse geometry cannot certify endpoints, inventory sharing or native paths.',
                    'Cached road screens cover snapshot obstacles only; all planned facility geometry is rechecked.',
                    'Explicitly document limited upgrades; do not silently waive conflicts.',
                    'Water/grade rejection requires a local design, never automatic repeated native submissions.'])


def deliver(out, result, plan, manifest):
    def table(headers, rows):
        def clean(v): return str(v).replace('|', '\\|').replace('\n', ' ')
        return '\n'.join('| '+' | '.join(map(clean, row))+' |'
                         for row in [headers, ['---']*len(headers), *rows])+'\n'
    counts = result['counters']
    atomic_write(out/'README.md', '# 全图离线预检\n\n本次仅处理文件，没有连接游戏。\n\n'+
        table(['设施', '道路', '执行任务', '离线道路缓存命中'],
              [[counts[k] for k in ('facilities','roads','jobs','road_cache_hits')]])+
        '\n[几何与接路问题](ISSUES.md) · [设施坐标](facilities.csv) · '
        '[城市供给](CITIES.md) · [线路](ROUTES.md) · [执行与变更范围](EXECUTION.md) · [计时](TIMING.md)\n\n'+
        '这是统一预检报告，不替代完整选址论证或原生预览。输入方案不会被改写。\n')
    g = result['geometry']
    atomic_write(out/'ISSUES.md', '# 需要处理的问题\n\n'+table(['类别','对象'],
        [['执行清单缺少地图指纹',x] for x in result['missing_manifest_identity']]+
        [['当前占地冲突',x] for x in g['footprint_conflicts']]+
        [['扩建预留冲突',x] for x in g['reservation_conflicts']]+
        [['现有建筑限制扩建',f'{k}: {v}'] for k,v in g['upgrade_existing_conflicts'].items()]+
        [['缺少尺寸',x] for x in g['missing_geometry']]+
        [['道路需要局部设计',r['id']+': '+str(r['rejections'])] for r in result['roads'] if not r['candidates']]))
    stream = io.StringIO(newline='')
    writer = csv.writer(stream); writer.writerow(['id','kind','x','y','rotation'])
    for row in plan.get('facilities', [])+plan.get('ports', []):
        writer.writerow([row['id'],row.get('kind'),row['position']['x'],row['position']['y'],row.get('rotation')])
    atomic_write(out/'facilities.csv', stream.getvalue())
    atomic_write(out/'CITIES.md', '# 城市需求\n\n'+table(['城市','需求（货物编号）'],
        [[c['name'], json.dumps(c.get('demand',{}),ensure_ascii=False)] for c in plan['cities']])+
        '\n## 全图供给上限\n\n'+table(['货品','需求','可供给','缺口'],
        [[s.get('name',s.get('cargo')),s.get('demand'),s.get('available'),s.get('gap')] for s in plan.get('supply',[])]))
    atomic_write(out/'ROUTES.md', '# 线路清单\n\n'+table(['编号','方式','来源','目的地'],
        [[r['id'],r.get('mode'),r.get('source',r.get('start')),r.get('destination',r.get('end'))]
         for r in plan.get('line_specs',plan.get('routes',[]))]))
    write_json(out/'execution_batches.json', result['batches'])
    write_json(out/'hub_sets.json', result['hub_sets'])
    atomic_write(out/'EXECUTION.md', '# 执行与局部重算\n\n'+
        f"变化任务 {len(result['changes']['changed'])}；包含依赖传播后 {len(result['changes']['affected'])}；移除 {len(result['changes']['removed'])}。\n\n"+
        '每批最多8项，仅建议顺序。不得把未变化项目或缓存视为已通过当前原生预览。\n\n'+
        '建造前：当前会话核验、实体重解析、实际入口与运输网络检查、重新预览、单次提交、独立读回。未知结果停止，不重发。\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('plan','snapshot','manifest','output'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    # Do not allow generated files to overwrite any input, including baseline.
    inputs = [args.plan,args.snapshot,args.manifest]+([args.baseline] if args.baseline else [])
    if any(p.resolve().is_relative_to(args.output.resolve()) for p in inputs):
        parser.error('output must be a separate directory outside all input file paths')
    timer = Timing()
    try:
        with timer.stage('read_inputs'):
            plan,snapshot,manifest = [json.loads(p.read_text('utf8')) for p in inputs[:3]]
            baseline = json.loads(args.baseline.read_text('utf8')) if args.baseline else None
        result = workflow(plan,snapshot,manifest,baseline,timer)
        result['input_digests'] = dict(plan=digest(plan),snapshot=digest(snapshot),manifest=digest(manifest))
        with timer.stage('write_delivery'):
            deliver(args.output,result,plan,manifest)
            write_json(args.output/'preflight.json',result)
        result_time = timer.result()
        write_json(args.output/'timing.json',result_time)
        atomic_write(args.output/'TIMING.md','# 本次离线流程计时\n\n'+
            f"墙钟 {result_time['wall_seconds']:.3f} 秒；只计当前调用，不包含勘探、原生预览或此前分析。\n\n"+
            '\n'.join(f"- {s['stage']}: {s['seconds']:.3f} 秒" for s in timer.rows)+'\n')
        print(json.dumps(dict(**result['counters'],requires_attention=result['requires_attention'],
                              seconds=result_time['wall_seconds'])))
    except Exception as exc:
        write_json(args.output/'failure.json',dict(error=str(exc),timing=timer.result()))
        raise


if __name__ == '__main__':
    main()
