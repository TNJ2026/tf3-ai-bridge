"""Compile shared hub groups and bounded review queues; never authorize construction."""


def compile_hub_sets(plan, road_reviews, geometry):
    facilities = {f['id']: f for f in plan.get('facilities', [])+plan.get('ports', [])}
    reviews = {r['id']: r for r in road_reviews}
    groups = []
    for hub in plan.get('hubs', []):
        members = set(hub['facilities'].values())
        if members - facilities.keys():
            raise ValueError('Unknown hub facility: '+str(members-facilities.keys()))
        if hub.get('kind') == 'production':
            required = ('heliport','warehouse','truck','bus','road_depot','road_maintenance') if 'heliport' in hub['facilities'] else ('helipad','helipad2','warehouse','truck')
        else:
            # Previously captured city groups may lack the new optional roles.
            # Current default templates are independently checked before planning.
            required = ('heliport','warehouse','truck')
        groups.append(dict(owners={str(hub['owner'])}, members=members,
                           missingRoles=set(required)-hub['facilities'].keys()))
    # Shared hubs become a single execution group, including transitive sharing.
    merged = []
    for group in groups:
        while True:
            matching = next((g for g in merged if g['members'] & group['members']), None)
            if matching is None:
                break
            merged.remove(matching)
            for key in ('members','owners','missingRoles'):
                group[key] |= matching[key]
        merged.append(group)
    result = []
    for group in sorted(merged, key=lambda g: sorted(g['owners'])):
        members = group['members'];issues = []
        roads = [r for r in plan.get('roads', [])
                 if r.get('to_facility') in members or r.get('from_facility') in members]
        access = {r[k] for r in roads for k in ('from_facility','to_facility') if k in r}
        for role in sorted(group['missingRoles']):
            issues.append(dict(kind='missing_role', subject=role))
        for fid in sorted(members):
            if facilities[fid].get('kind') in ('truck','heliport') and fid not in access:
                issues.append(dict(kind='missing_access_road', subject=fid))
        for road in roads:
            if not reviews.get(road['id'], {}).get('candidates'):
                issues.append(dict(kind='road_requires_design', subject=road['id']))
        for kind in ('footprint_conflicts','reservation_conflicts'):
            for pair in geometry.get(kind, []):
                if members.intersection(pair):
                    issues.append(dict(kind=kind, subject=pair))
        for fid in geometry.get('missing_geometry', []):
            if fid in members:
                issues.append(dict(kind='missing_geometry', subject=fid))
        for fid, entities in geometry.get('upgrade_existing_conflicts', {}).items():
            if fid in members:
                issues.append(dict(kind='upgrade_existing_conflicts', subject=fid, entities=entities))
        queue = [] if issues else [dict(road=r['id'], candidateIndexes=list(range(min(3, len(reviews[r['id']]['candidates'])))),
                                       maxNativePreviews=3, onKnownRejection='next_candidate',
                                       onUnknownResult='stop_and_reconcile') for r in roads]
        result.append(dict(id='HUBSET:'+','.join(sorted(group['owners'])), owners=sorted(group['owners']),
                           sharedWarehousePlans=[dict(owner=str(h['owner']),
                               primaryWarehouse=h['facilities'].get('warehouse'),
                               stationFacilities={role:fid for role,fid in h['facilities'].items()
                                                  if role in ('truck','heliport','helipad','helipad2')},
                               primaryStockList=None,inventoryVerified=False,
                               rule='Each cargo facility covers designated warehouse; resolve canonical inventory after build')
                               for h in plan.get('hubs',[])if str(h['owner'])in group['owners']],
                           facilities=sorted(members), roads=sorted(r['id'] for r in roads),
                           status='needs_design' if issues else 'joint_native_preview_required',
                           issues=issues, previewQueue=queue, constructionReady=False,
                           requiredNativeChecks=['joint_facility_and_road_layout','actual_entrance_and_transport_network',
                                                 'shared_warehouse_inventory','bidirectional_road_paths','upgrade_clearance']))
    return result
