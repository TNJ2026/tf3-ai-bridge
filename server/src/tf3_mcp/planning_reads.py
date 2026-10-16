"""Bounded independent planning reads; never replay an unknown transport outcome."""
from __future__ import annotations

import copy
import json

from .ui_log import validate_read_batch


def chunks(requests):
    """Validate the entire round before publication, including encoded ingress size."""
    if not isinstance(requests, list) or not 1 <= len(requests) <= 256:
        raise ValueError('A planning round requires 1-256 independent reads')
    groups, group = [], []
    for row in copy.deepcopy(requests):
        validate_read_batch({'requests': [row]})
        def size(rows):
            return len(('0' * 32 + ' read_batch ' + json.dumps(
                {'requests': rows}, separators=(',', ':'), sort_keys=True)).encode('utf-8'))
        if size([row]) > 8192:
            raise ValueError('Planning read exceeds receiver input limit')
        if group and (len(group) == 8 or size(group + [row]) > 8192):
            groups.append(group)
            group = []
        group.append(row)
    groups.append(group)
    return groups


async def read_planning(call, requests):
    groups = chunks(requests)
    results, receipts = [], []

    async def batch(rows):
        response = await call('read_batch', {'requests': rows})
        items = response.get('results')
        if (response.get('readBatchVersion') != 1 or response.get('readOnly') is not True
                or response.get('count') != len(rows) or not isinstance(items, list)
                or len(items) != len(rows)):
            raise ValueError('Invalid batch receipt; do not retry')
        for i, (request, item) in enumerate(zip(rows, items)):
            if (item.get('index') != i or item.get('command') != request['command']
                    or type(item.get('ok')) is not bool or type(item.get('executed')) is not bool
                    or (item['ok'] and (not item['executed'] or 'result' not in item))):
                raise ValueError('Invalid batch item receipt; do not retry')
        receipts.append({'count': len(rows), 'elapsedMs': response.get('elapsedMs'),
                         'complete': response.get('complete'),
                         'errors': [{'index': i, 'command': item['command'],
                                     'error': item.get('error'), 'executed': item['executed']}
                                    for i, item in enumerate(items) if not item['ok']]})
        return items

    for group in groups:
        items = await batch(group)
        for request, item in zip(group, items):
            # Only explicit receiver limits permit one new, smaller read. Native
            # errors, malformed receipts and transport timeouts never trigger retry.
            limited = (not item['ok'] and (
                (item.get('error') == 'time_budget_exceeded' and not item['executed'])
                or (item.get('error') == 'response_size_limit' and item['executed'])))
            if limited and len(group) > 1:
                item = (await batch([request]))[0]
            results.append(dict(item, index=len(results)))
    return {'readOnly': True, 'atomicSnapshot': False,
            'complete': all(row['ok'] for row in results), 'count': len(results),
            'results': results, 'batchCount': len(receipts), 'batches': receipts}
