"""Stable planning identities; no game/entity state."""
import hashlib
import json
import re


def facility_id(owner, role, context='main'):
    parts = [str(v) for v in (owner, context, role)]
    if any(not v for v in parts):
        raise ValueError('owner, context and role are required')
    label = '_'.join(re.sub(r'[^\w-]', '-', v) for v in parts)
    suffix = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode('utf8')).hexdigest()[:12]
    return label+'_'+suffix


def unique_ids(rows):
    seen = set()
    for row in rows:
        name = row.get('id')
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError('missing/duplicate planning ID: '+str(name))
        seen.add(name)
    return seen
