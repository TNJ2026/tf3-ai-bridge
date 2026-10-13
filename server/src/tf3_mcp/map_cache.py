"""Revision-aware map cache. Polling is explicit; stale data is never called current."""
from __future__ import annotations
import asyncio
import copy
import json
import os
import time
from pathlib import Path


class MapCache:
    def __init__(self, fetch, path=None, interval=15):
        self.fetch, self.path, self.interval = fetch, Path(path) if path else None, interval
        self.snapshot = None
        self.updated = 0.
        self.key = None
        self.error = None
        self.task = None
        self.lock = asyncio.Lock()
        self.generation = 0
        self.wake = asyncio.Event()

    def invalidate(self):
        self.generation += 1
        self.wake.set()
        self.updated = 0
        self.snapshot = None  # force terrain and entities to be read after our mutations

    async def refresh(self, start, end, *, spacing=100, force=False):
        key=(start,end,spacing)
        async with self.lock:
            if not force and not self.error and key==self.key and self.snapshot and time.time()-self.updated<self.interval:
                return copy.deepcopy(self.snapshot), self.status(hit=True)
            generation=self.generation
            old=self.snapshot if key==self.key else None
            args=dict(start_construction=start,end_construction=end,spacing=spacing,whole_map=True)
            # Full resync every five minutes also guards a save switch without revision changes.
            if old and time.time()-old.get('_fullReadAt',0)<300:
                args.update(domain=old['domain'],revisions=old['revisions'],terrain_revisions=old['terrainRevisions'])
            try:
                response=await self.fetch(args)
                if generation!=self.generation:
                    raise RuntimeError('map changed during refresh; retry with a fresh snapshot')
                if response.get('delta'):
                    if not old or old['domain']!=response['domain']:
                        raise ValueError('delta has no matching base')
                    if response.get('state',{}).get('tickCount',0)<old.get('state',{}).get('tickCount',0):
                        self.invalidate()
                        raise ValueError('game time rewound; full refresh required')
                    rows={r['entity']:r for r in old['obstacles'] if str(r['entity']) in response['revisions']}
                    # Changed entities may now be vegetation/outside bounds: remove before applying updates.
                    for ident,rev in response['revisions'].items():
                        if old['revisions'].get(ident)!=rev:rows.pop(int(ident),None)
                    rows.update({r['entity']:r for r in response['obstacles']})
                    if response.get('grid') is None:response['grid']=old['grid']
                    response['obstacles']=list(rows.values())
                    response['_fullReadAt']=old['_fullReadAt']
                else:
                    if response.get('grid') is None:raise ValueError('full snapshot has no terrain')
                    response['_fullReadAt']=time.time()
                self.snapshot,self.key,self.updated,self.error=response,key,time.time(),None
                if self.path:
                    self.path.parent.mkdir(parents=True,exist_ok=True)
                    tmp=self.path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(dict(updated=self.updated,key=key,snapshot=response)),encoding='utf-8')
                    os.replace(tmp,self.path)
                return copy.deepcopy(response),self.status(hit=False)
            except Exception as exc:
                self.error=str(exc)
                raise

    def status(self,hit=False):
        return dict(hit=hit,ageSeconds=round(time.time()-self.updated,2) if self.updated else None,
                    polling=bool(self.task and not self.task.done()),intervalSeconds=self.interval,
                    error=self.error,entities=len(self.snapshot['obstacles']) if self.snapshot else 0,
                    freshness='polled; force refresh and native preview before building')

    async def start(self,start,end,spacing=100):
        await self.stop()
        await self.refresh(start,end,spacing=spacing,force=True)
        async def poll():
            while True:
                try:await asyncio.wait_for(self.wake.wait(), self.interval)
                except asyncio.TimeoutError:pass
                self.wake.clear()
                try:await self.refresh(start,end,spacing=spacing,force=True)
                except Exception:break  # retain error; never poll a failed receiver automatically
        self.task=asyncio.create_task(poll())
        return self.status()

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
            self.task=None
