"""Roadside placement using existing named interfaces, with durable caller logging.

This workflow never retries a dispatched request. A split and a construction are
separate commits. Failure after a split leaves a documented preparation point;
it does not split another road or silently replay the first operation.
"""
from __future__ import annotations

import math
from .planning_reads import read_planning
from .frontage_planning import (RESOURCES, candidates, curve, project, external_port,
    native_collider, footprint_contains, safe_preview, finite)


class RoadsidePlacement:
    def __init__(self, call, content, record, checkpoint):
        self.call, self.content = call, content
        self.record, self.checkpoint = record, checkpoint
        self.cache = {}

    async def component(self, entity, name):
        key = (entity,name)
        if key not in self.cache:
            result = await self.call('get_entity', {'id':entity,'components':[name]})
            components = result['components']
            # Lua serializes an empty component map as []; this is an explicit
            # absent component, unlike missing/truncated data.
            if components == []: components = {}
            self.cache[key] = components.get(name)
        return self.cache[key]

    async def components(self, entities, name):
        missing = list(dict.fromkeys(e for e in entities if (e, name) not in self.cache))
        if len(missing) == 1:
            await self.component(missing[0], name)
        elif missing:
            result = await read_planning(self.call, [
                {'command': 'get_entity', 'arguments': {'id': e, 'components': [name]}}
                for e in missing])
            self.record.setdefault('planningReads', []).append(result)
            self.checkpoint()
            if not result['complete']:
                raise ValueError('Incomplete planning component batch; inspect planningReads')
            for entity, row in zip(missing, result['results']):
                components = row['result']['components']
                self.cache[(entity, name)] = (components or {}).get(name)
        return [self.cache[(e, name)] for e in entities]

    async def profile(self, kind, size):
        if kind not in RESOURCES or type(size) is not int or size not in (1,2,3):
            raise ValueError('Unsupported facility kind/size')
        profile = {'kind':kind, 'size':size, 'resource':RESOURCES[kind]}
        if kind in ('heliport','helipad','road_depot','tram_depot'):
            profile.update(native_collider(self.content,kind))
        else:
            # Screening envelope only. Modular geometry is finally decided by
            # native preview; this is not a collision-free or upgrade assertion.
            profile.update(bounds=[-25*size,25*size,-22,65], boundsEstimated=True)
        if kind in ('heliport','helipad'): return profile
        inventory = await self.call('list_facilities',{})
        for item in inventory['items']:
            if item['resource'] != profile['resource']: continue
            con = await self.component(item['entity'],'CONSTRUCTION')
            modules = con['params'].get('modules',{})
            modules = list(modules.values()) if isinstance(modules,dict) else modules
            if kind.endswith('station'):
                file = 'cargo_platform.module' if kind=='cargo_station' else 'passenger_platform.module'
                platforms = [m for m in modules if m['name'].endswith(file)]
                expected = {1:2,2:4,3:8}[size]
                if len(platforms) != expected or len(modules) != expected+1: continue
            elif modules: continue
            edges = await self.components(con['frozenEdges'], 'BASE_EDGE')
            profile.update(port=external_port(con,edges),sourceEntity=item['entity'],
                           portBasis='fresh native external port in matching facility local coordinates')
            return profile
        raise ValueError('No matching native facility exemplar; port geometry is unknown (not guessed)')

    async def plan(self, *, kind, edge=None, size=1, param=None, x=None, y=None, side='auto', search=True):
        self.cache.clear()
        if (x is None)!=(y is None): raise ValueError('Both x and y are required')
        state = await self.call('get_validation_state',{})
        if state.get('pending') or state.get('frontageDiscoveryPolicy')!='displaced-discovery-node-v5':
            raise ValueError('Fresh v5 receiver without pending required')
        if state.get('frontageHeightPolicy')!='native-foundation-alignment-v1':
            raise ValueError('Loaded receiver lacks native foundation alignment; load updated bridge before using this planner')
        profile = await self.profile(kind,size)
        if edge is None:
            if x is None or param is not None: raise ValueError('Road selection requires x/y, or an explicit edge')
            nearby = await self.call('find_nearby',{'x':x,'y':y,'radius':150,'limit':100})
            if len(nearby['edges'])>=100: raise ValueError('Road selection survey truncated')
            choices=[]
            for index, item in enumerate(nearby['edges']):
                if index % 8 == 0:
                    await self.components([e['id'] for e in nearby['edges'][index:index+8]], 'BASE_EDGE')
                e=await self.component(item['id'],'BASE_EDGE')
                if int(e['roadType'])!=1 or int(e['type'])!=0 or e['objects'] or '/constructions/' in e['roadTemplate']:continue
                t=project(e,x,y);p,_=curve(e,t)
                choices.append((math.hypot(p['x']-x,p['y']-y),item['id']))
            if not choices:raise ValueError('No ordinary road near target')
            edge=min(choices)[1]
        road = await self.component(edge,'BASE_EDGE')
        if not road or int(road['roadType'])!=1 or int(road['type'])!=0 or road['objects']:
            raise ValueError('Select an ordinary ground street without edge objects')
        if '/constructions/' in road['roadTemplate']:
            raise ValueError('Construction-owned roads require a separate design')
        for cfg in await self.components([road['node0'],road['node1']], 'BASE_NODE_CONFIG'):
            if cfg and (cfg.get('userModifiedLaneConnections') or cfg.get('userModifiedTrafficLightStates')
                        or cfg.get('trafficLightConfig',{}).get('states')):
                raise ValueError('Custom endpoint configuration cannot be replaced by direct frontage')
        modes = ('5','6') if kind=='tram_depot' else ('2','3','4')
        for direction in (True,False):
            if not any(l['forward']==direction and all(l['transportModes'].get(m) for m in modes)
                       for l in road['laneConfigs']):
                raise ValueError('Compatible lanes required in both directions')
        if param is not None and (x is not None or y is not None):
            raise ValueError('Choose param OR x/y')
        param = project(road,x,y) if x is not None and y is not None else (.5 if param is None else param)
        plan = {'profile':profile,'edge':edge,'roadBefore':road,'requestedParam':param,
                'candidates':[], 'selected':None, 'nativePreviewPassed':False,
                'method':'native_auto_link' if kind in ('heliport','helipad') else 'split_then_native_frontage'}
        self.record['plan'] = plan
        for candidate in candidates(road,profile,param=param,side=side,search=search):
            plan['candidates'].append(candidate)
            ground = await self.call('get_terrain',{'x':candidate['x'],'y':candidate['y']})
            candidate['terrain'] = ground
            if not ground.get('valid') or ground.get('water'):
                candidate['rejected']='water_or_unknown_terrain';continue
            candidate['foundationHeightAdjustment']=candidate['z']-ground['height']
            radius = max(100,math.hypot(max(abs(v) for v in profile['bounds'][:2]),
                                      max(abs(v) for v in profile['bounds'][2:]))+60)
            near = await self.call('find_nearby',{'x':candidate['x'],'y':candidate['y'],
                                               'radius':radius,'limit':100})
            # No complete town-building bounds are exposed by this query. Stay
            # out of occupied town areas instead of treating the count as shapes.
            if near['townBuildings'] or len(near['edges'])>=100 or len(near['constructions'])>=100:
                candidate['rejected']='occupied_or_truncated_survey';continue
            if any(footprint_contains(candidate,profile['bounds'],c['position'],margin=30)
                   for c in near['constructions']):
                candidate['rejected']='nearby_construction';continue
            obstruction = False
            for index, item in enumerate(near['edges']):
                if index % 8 == 0:
                    await self.components([e['id'] for e in near['edges'][index:index+8]], 'BASE_EDGE')
                other = await self.component(item['id'],'BASE_EDGE')
                # Include the target curve too: a sharp bend may enter the
                # footprint even though its tangent at the chosen point does not.
                for i in range(41):
                    p,_ = curve(other,i/40)
                    if footprint_contains(candidate,profile['bounds'],p,margin=candidate['roadHalfWidth']-.05):
                        obstruction=True;break
                if obstruction: break
            if obstruction:
                candidate['rejected']='road_envelope_intersects_footprint';continue
            plan['selected']=candidate
            cmd,args=self.args(plan)
            preflight=self.quote(await self.call(cmd,args))
            candidate['nativeSitingPreview']=preflight
            if not self.preflight_fit(preflight,edge,plan['method']=='split_then_native_frontage'):
                candidate['rejected']='native_siting_rejection'
                plan['selected']=None
                continue
            break
        self.checkpoint()
        return plan

    def args(self, plan, node=None):
        p,f = plan['selected'],plan['profile']
        args = {k:p[k] for k in ('x','y','rotation')}
        if f['kind'] in ('heliport','helipad'):
            return 'build_'+f['kind'],dict(args,z=p['z'])
        if node is not None: args.update(frontage_node=node,z=p['z'])
        if f['kind'].endswith('depot'):
            return 'preview_depot',dict(args,carrier='TRAM' if f['kind']=='tram_depot' else 'ROAD')
        return 'preview_station',dict(args,cargo=f['kind']=='cargo_station',size=f['size'])

    @staticmethod
    def quote(result):
        return dict(result.get('check',result),preview_token=result.get('preview_token'))

    @staticmethod
    def preflight_fit(preview,edge,will_split):
        if not finite(preview.get('cost')) or preview['cost']<0:return False
        if not will_split:return safe_preview(preview)
        blocking=preview.get('blocking') or {}
        return not (preview.get('critical') or preview.get('warnings') or preview.get('unexpected_removals')
            or blocking.get('townBuildings') or blocking.get('constructions')
            or any(e!=edge for e in preview.get('collisions',[]))
            or any(e!=edge for e in blocking.get('streets',[]))
            or (preview.get('blocked') and not preview.get('collisions'))
            or (preview.get('placementBlocked') and not preview.get('collisions')))

    async def pay(self, command, quote, budget, floor, **extra):
        if not safe_preview(quote): raise ValueError('Current native preview rejected; no commit')
        state = await self.call('get_game_state',{})
        validation = await self.call('get_validation_state',{})
        if validation.get('pending') or state['speedup']!=0:
            raise ValueError('Paused, uncontested current session required')
        spent = self.record.get('quotedCommitted',0)
        if spent+quote['cost']>budget or state['balance']-quote['cost']<=floor:
            raise ValueError('Current quote exceeds budget or cash floor')
        result = await self.call(command,dict(preview_token=quote['preview_token'],**extra))
        self.record['quotedCommitted']=spent+quote['cost']
        self.checkpoint()
        return result

    async def build(self, plan, *, budget, floor=1500000, backup, allow_unpriced_split=False):
        if not finite(budget) or budget<=0 or not finite(floor) or floor<0:
            raise ValueError('Explicit finite budget and nonnegative floor required')
        if not plan['selected']: raise ValueError('No safe bounded candidate found')
        state = await self.call('get_game_state',{})
        if state['speedup']!=0: raise ValueError('Pause required; speed is never changed automatically')
        p,f = plan['selected'],plan['profile']
        cmd,args = self.args(plan)
        first = self.quote(await self.call(cmd,args))
        self.record['initialBuildingPreview']=first
        # This is an estimate at natural height. The final bound proposal has its
        # own price and approval; expected road collisions here do not approve it.
        if not finite(first.get('cost')) or first['cost']<0:
            raise ValueError('Building price unavailable; no road preparation')
        if not self.preflight_fit(first,plan['edge'],plan['method']=='split_then_native_frontage'):
            raise ValueError('Building preflight has non-target obstacles or errors; no split')
        node = None
        if plan['method']=='split_then_native_frontage':
            split = await self.call('preview_road_graph',{'graph':{
                'nodes':[{'split':{'edge':plan['edge'],'param':p['param']}}], 'edges':[]}})
            self.record['splitPreview']=split
            if (split.get('structural_only') is not True or split.get('nativePreviewPassed') is not False
                    or split.get('collisionsUnchecked') is not True):
                raise ValueError('Unexpected split preview contract')
            # Cutting a road along its exact existing curve is explicitly
            # structural-only in this API. Do not relabel it as native preview.
            self.check_split(split,allow_unpriced_split)
            full = first['cost']+split.get('cost',0)
            self.record['splitPriceKnown']=finite(split.get('cost'))
            self.record['unpricedSplitExplicitlyAuthorized']=allow_unpriced_split
            self.record['fullCostKnown']=finite(split.get('cost'))
            self.checkpoint()
            if full>budget or state['balance']-full<=floor:
                raise ValueError('Complete minimum project estimate exceeds funds')
        else:
            if not safe_preview(first): raise ValueError('Air facility native preview rejected')
            if first['cost']>budget or state['balance']-first['cost']<=floor:
                raise ValueError('Complete project exceeds funds')
        saved = await self.call('save_game',{'slot':backup,'overwrite':False})
        if not saved.get('verified'): raise ValueError('Backup not verified')
        self.record['backup']=saved;self.checkpoint()
        if plan['method']=='split_then_native_frontage':
            # Backup latency can consume preview TTL; refresh the same read-only
            # preview before the single commit, never replay the commit.
            split = await self.call('preview_road_graph',{'graph':{
                'nodes':[{'split':{'edge':plan['edge'],'param':p['param']}}], 'edges':[]}})
            self.check_split(split,allow_unpriced_split)
            if split.get('cost',0)+first['cost']>budget:
                raise ValueError('Refreshed split price exceeds full budget')
            s = await self.call('get_game_state',{})
            if s['balance']-split.get('cost',0)-first['cost']<=floor:
                raise ValueError('Complete project no longer affordable')
            if finite(split.get('cost')):
                b = await self.pay('commit_road_graph',split,budget,floor,backup_save=backup)
            else:
                # Only an explicit caller opt-in authorizes this unknown cost.
                # Do not synthesize a zero quote or count it as priced spending.
                v=await self.call('get_validation_state',{})
                if v.get('pending') or s['speedup']!=0: raise ValueError('Pending or unpaused before split')
                self.record['unpricedOperations']=[{'command':'commit_road_graph','cost':None,
                    'preview_token':split['preview_token'],'budgetGuaranteed':False}]
                self.checkpoint()
                b=await self.call('commit_road_graph',dict(preview_token=split['preview_token'],backup_save=backup))
            self.record['splitResult']=b;self.record['stage']='road_prepared';self.checkpoint()
            if not b.get('verified'): raise ValueError('Split outcome unverified; never retry')
            near = await self.call('find_nearby',{'x':p['target']['x'],'y':p['target']['y'],'radius':5,'limit':100})
            nodes = [n for n in near['nodes'] if n['distance']<.1 and len(n['connections'])==2]
            if len(nodes)!=1: raise ValueError('Cannot uniquely resolve prepared frontage')
            node = nodes[0]['id'];self.record['preparedNode']=node;self.checkpoint()
        cmd,args = self.args(plan,node)
        preview = self.quote(await self.call(cmd,args))
        self.record['finalPreview']=preview;self.checkpoint()
        b = await self.pay('commit_facility' if node is None else 'commit_structure',preview,budget,floor)
        self.record['buildingResult']=b;self.record['stage']='built_pending_access';self.checkpoint()
        if not b.get('built') or not b.get('verified'): raise ValueError('Building outcome unverified; never retry')
        if node is None:
            access = await self.call('get_facility_access',{'entity':b['entity'],'person_graph':True,'person_geometry':False})
            self.record['access']=access
            if not access.get('complete') or not access.get('automaticRoadLinkObserved'):
                raise ValueError('Native automatic road access not verified')
        else:
            self.cache.clear()
            con = await self.component(b['construction'],'CONSTRUCTION')
            external = []
            for eid in con['frozenEdges']:
                e = await self.component(eid,'BASE_EDGE')
                external.extend(e[f'node{i}'] for i in (0,1) if e[f'node{i}'] not in con['frozenNodes'])
            near = await self.call('find_nearby',{'x':p['target']['x'],'y':p['target']['y'],'radius':5,'limit':100})
            shared = [n for n in near['nodes'] if n['id'] in external and n['distance']<.1 and len(n['connections'])==3]
            if len(shared)!=1: raise ValueError('Shared native entrance not uniquely verified')
            n=shared[0];checks=[];self.record['paths']=checks
            for mode in (('TRAM','ELECTRIC_TRAM') if f['kind']=='tram_depot' else ('BUS','TRUCK')):
                for a in n['connections']:
                    for z in n['connections']:
                        if a['edge']==z['edge']: continue
                        check = await self.call('check_road_junction_path',{'node':n['id'],
                            'from_edge':a['edge'],'to_edge':z['edge'],'mode':mode})
                        checks.append(check);self.checkpoint()
                        if not check.get('pathFound') or not check.get('directPathVerified'):
                            raise ValueError('Native directed entrance path failed')
        self.record['stage']='access_verified';self.checkpoint()
        return b

    @staticmethod
    def check_split(split,allow_unpriced):
        if (split.get('ok') is not True or not split.get('preview_token') or
                any(split.get(k) for k in ('critical','blocked','placementBlocked','collisions','warnings'))):
            raise ValueError('Split structural check rejected')
        if not finite(split.get('cost')) and not allow_unpriced:
            raise ValueError('Split price unavailable; explicit unpriced test authorization required')
        if finite(split.get('cost')) and split['cost']<0: raise ValueError('Invalid split price')
