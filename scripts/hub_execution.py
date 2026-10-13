"""Dependency-ordered, single-attempt execution of a prepared hub collection."""
import time
from fullmap_batch import StopBatch, quote, unfinished
from batch_connections import road_preview_ok

def strict_road_preview(result):
    return result.get('ok') is True and road_preview_ok(result) and not any(result.get(k) for k in
        ('infos', 'warnings', 'messages', 'collisions', 'placementBlocked'))

async def execute_collection(batch, *, preview=False):
    """The adapter owns geometry; this runner owns submission and recovery policy."""
    await batch.session()
    batch.tasks_all = batch.tasks()
    # No global historical-ledger gate; individual submissions are never replayed.
    items = batch.ledger['items']
    scope = {t['id'] for t in batch.tasks_all} | {r['id'] for r in batch.p['roads']}
    skipped = [k for k in scope if items.get(k,{}).get('attempts') and
               items[k].get('status') not in ('static_verified','connection_verified')]
    if skipped:
        # Do not replay or claim success. Unrelated historical operations are ignored.
        return {'phase':'skipped_submitted_operations','accepted':False,'skipped':sorted(skipped)}
    has_submissions = any(v.get('attempts', 0) for v in items.values())
    # Preserve past submission records without re-auditing the whole collection.
    for task in batch.tasks_all:
        items.setdefault(task['id'], {'attempts': 0})
    for task in batch.tasks_all:
        item = items[task['id']]
        if not item['attempts']:
            result = await batch.clone(task)
            item.update(preview=result, status='preview_ready' if result.get('safe') else 'preview_blocked')
            batch.flush()
            if not result.get('safe'):
                raise StopBatch('Facility preview rejected: '+task['id'])
    # A corridor preview of an empty site is invalid once our own roads exist.
    if not has_submissions:
        await batch.preflight_corridors()
    if preview:
        return {'phase': 'preview', 'destinationPortsPending': True, 'accepted': False}
    if not has_submissions:
        await batch.save('before')
    for task in batch.tasks_all:
        item = items[task['id']]
        if item['attempts']:
            continue
        await batch.session()
        item.update(attempts=1, status='commit_started', intentTime=time.time())
        batch.flush()
        # clone performs a FRESH strict preview and commit in the same engine call.
        item['commit'] = await batch.clone(task, True)
        batch.flush()
        if not item['commit'].get('commit', {}).get('built'):
            raise StopBatch('Unknown facility submission: '+task['id'])
        await verify_facility(batch, task, item)
    for spec in batch.p['roads']:
        item = items.setdefault(spec['id'], {'attempts': 0, 'kind': 'connection'})
        if item['attempts']:
            continue
        await batch.session()
        args, resolved = await batch.resolve(spec)
        if args is None:
            raise StopBatch('Missing road endpoint: '+spec['id'])
        result = await batch.eval('return B.json.encode(B.commands.build_road(B.json.decode('+
            quote(dict(args, preview=True))+')))')
        item.update(input=args, resolved=resolved, preview=result,
                    status='preview_ready' if strict_road_preview(result) else 'preview_blocked')
        batch.flush()
        if not strict_road_preview(result):
            # Do not run dependent roads or quietly declare completion.
            raise StopBatch('Road preview rejected: '+spec['id'])
        fresh, identity = await batch.resolve(spec)
        if fresh != args or identity != resolved:
            raise StopBatch('Road endpoints changed after preview')
        item.update(attempts=1, status='commit_started', intentTime=time.time())
        batch.flush()
        item['commit'] = await batch.eval('return B.json.encode(B.commands.build_road(B.json.decode('+
            quote(dict(args, preview=False))+')))')
        batch.flush()
        if item['commit'].get('built') is not True:
            raise StopBatch('Unknown road submission: '+spec['id'])
        item['audit'] = await batch.audit_road(item)
        if not item['audit'].get('verified'):
            await batch.complete_junctions(item)
        if not item['audit'].get('verified'):
            raise StopBatch('Road readback failed: '+spec['id'])
        item['status'] = 'connection_verified'
        batch.flush()
    # No 'complete' save or accepted status until the unified audit passes.
    return await batch.accept_collection()

async def verify_facility(batch, task, item):
    result = await batch.facility(task, 'verify')
    audit = result.get('audit', {})
    item['audit'] = audit
    norm = lambda modules: {str(k): (v['name'], v.get('variant', 0)) for k, v in modules.items()}
    good = audit.get('staticVerified') and norm(audit.get('params', {}).get('modules', {})) == norm(task['expectedParams']['modules'])
    item['status'] = 'static_verified' if good else 'needs_reconciliation'
    batch.flush()
    if not good:
        raise StopBatch('Facility/module readback failed: '+task['id'])
