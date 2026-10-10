"""Install one bounded diagnostic generation; does not reload/control the game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

from validate_bridge_compile import check_bridge_compile
from network_rejection_recovery import prepare_recovery, lua_literal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mod-content', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--on-demand', action='store_true', help='No preallocated slots or idle slot consumption; experimental')
    parser.add_argument('--network-rejection-receipt', type=Path, help='Explicit audited legacy native pre-dispatch error; never a generic pending reset')
    parser.add_argument('--recovery-identity-survey', type=Path)
    parser.add_argument('--network-rejection-source', type=Path, help='Exact reviewed source image for legacy pre-dispatch enumeration rejection')
    parser.add_argument('--allow-recovery-industry-additions', action='store_true', help='Opt-in: retain every pinned original object unchanged, audit newly added industries; never permit removals or moves')
    args = parser.parse_args()
    if bool(args.network_rejection_receipt) != bool(args.recovery_identity_survey):
        parser.error('Recovery requires both original receipt and completed native identity survey')
    if args.allow_recovery_industry_additions and not args.network_rejection_receipt:
        parser.error('Industry additions policy requires an audited recovery receipt')
    source = Path(__file__).resolve().parents[1] / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'
    target = args.mod_content.resolve() / 'bridge.script.lua'
    if not target.is_file():
        raise SystemExit('Expected existing installed bridge script')
    text = source.read_text(encoding='utf-8')
    assert text.count('local HEADLESS_GENERATION = "disabled"') == 1
    assert 'local ENABLE_FIRST_READ_PROBE = false' in text
    assert 'local ENABLE_RESOURCE_INGRESS_PROBE = false' in text
    compile_check = check_bridge_compile(text)
    generation = uuid.uuid4().hex
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / ('bridge.before.' + generation + '.lua')).write_bytes(target.read_bytes())
    directory = target.parent / 'headless' / generation
    directory.mkdir(parents=True, exist_ok=False)
    for slot in range(1, 1 if args.on_demand else 1025):
        (directory / f'{slot}.lua').write_bytes(b'return ""\n')
    data = text.replace('local HEADLESS_GENERATION = "disabled"',
                        f'local HEADLESS_GENERATION = "{generation}"', 1)
    if args.on_demand:
        assert data.count('local HEADLESS_ON_DEMAND = false')==1
        data=data.replace('local HEADLESS_ON_DEMAND = false','local HEADLESS_ON_DEMAND = true',1)
    recovery = None
    if args.network_rejection_receipt:
        recovery = prepare_recovery(args.network_rejection_receipt, args.recovery_identity_survey, args.network_rejection_source,
                                    allow_industry_additions=args.allow_recovery_industry_additions)
        assert data.count('local NETWORK_REJECTION_MIGRATION = nil') == 1
        data = data.replace('local NETWORK_REJECTION_MIGRATION = nil',
                            'local NETWORK_REJECTION_MIGRATION = ' + lua_literal(recovery), 1)
    installed_compile_check = check_bridge_compile(data)
    data=data.encode('utf-8')
    temp = target.with_name('bridge.script.lua.' + generation + '.tmp')
    temp.write_bytes(data); os.replace(temp, target)
    assert target.read_bytes() == data
    result = dict(generation=generation, slots=None if args.on_demand else 1024,
                  mode='demand' if args.on_demand else 'bounded', intervalSeconds=1 if args.on_demand else 2,
                  installedSha256=hashlib.sha256(data).hexdigest(),
                  modContent=str(target.parent), status='installed_requires_fresh_load',
                  worldModified=False, reloadPerformed=False)
    if recovery:
        result['legacyRejectionMigration'] = recovery
    result['compilePreflight'] = compile_check
    result['installedCompilePreflight'] = installed_compile_check
    (args.evidence / 'deployment.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
