"""Install a receiver matched to its resource mount; never reloads the game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

from validate_bridge_compile import check_bridge_compile
from network_rejection_recovery import prepare_recovery, lua_literal


def select_receiver_mode(mod_content, mode='auto', on_demand=False):
    """Downloaded mounts did not discover post-startup request files in live tests."""
    downloaded = 'mod.io' in {part.lower() for part in Path(mod_content).resolve().parts}
    if on_demand:
        if mode not in ('auto', 'demand'):
            raise ValueError('--on-demand conflicts with --mode indexed')
        mode = 'demand'
    if mode == 'auto':
        mode = 'userdata' if downloaded else 'demand'
    if mode not in ('indexed', 'demand', 'userdata'):
        raise ValueError('Unknown receiver mode')
    if downloaded and mode == 'demand':
        raise ValueError('mod.io mounts require userdata or indexed mode: newly created demand files were not discovered')
    return mode, downloaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mod-content', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--mode', choices=('auto', 'demand', 'indexed', 'userdata'), default='auto',
                        help='auto: reusable userdata for mod.io, demand for local development mounts')
    parser.add_argument('--on-demand', action='store_true', help='Legacy alias for --mode demand; rejected on mod.io')
    parser.add_argument('--source', type=Path, help='Optional matching bridge source with receiver disabled; defaults to repository source')
    parser.add_argument('--network-rejection-receipt', type=Path, help='Explicit audited legacy native pre-dispatch error; never a generic pending reset')
    parser.add_argument('--recovery-identity-survey', type=Path)
    parser.add_argument('--network-rejection-source', type=Path, help='Exact reviewed source image for legacy pre-dispatch enumeration rejection')
    parser.add_argument('--allow-recovery-industry-additions', action='store_true', help='Opt-in: retain every pinned original object unchanged, audit newly added industries; never permit removals or moves')
    args = parser.parse_args()
    try:
        mode, downloaded = select_receiver_mode(args.mod_content, args.mode, args.on_demand)
    except ValueError as exc:
        parser.error(str(exc))
    on_demand = mode in ('demand', 'userdata')
    if bool(args.network_rejection_receipt) != bool(args.recovery_identity_survey):
        parser.error('Recovery requires both original receipt and completed native identity survey')
    if args.allow_recovery_industry_additions and not args.network_rejection_receipt:
        parser.error('Industry additions policy requires an audited recovery receipt')
    source = args.source or Path(__file__).resolve().parents[1] / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'
    target = args.mod_content.resolve() / 'bridge.script.lua'
    if not target.is_file():
        raise SystemExit('Expected existing installed bridge script')
    text = source.read_text(encoding='utf-8')
    assert text.count('local NO_GUI_GENERATION = "disabled"') == 1
    assert 'ENABLE_FIRST_READ_PROBE' not in text
    assert 'ENABLE_RESOURCE_INGRESS_PROBE' not in text
    compile_check = check_bridge_compile(text)
    generation = uuid.uuid4().hex
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / ('bridge.before.' + generation + '.lua')).write_bytes(target.read_bytes())
    directory = target.parent / 'no_gui' / generation
    directory.mkdir(parents=True, exist_ok=False)
    for slot in range(1, 1 if on_demand else 1025):
        (directory / f'{slot}.lua').write_bytes(b'return ""\n')
    data = text.replace('local NO_GUI_GENERATION = "disabled"',
                        f'local NO_GUI_GENERATION = "{generation}"', 1)
    if on_demand:
        assert data.count('local NO_GUI_ON_DEMAND = false')==1
        data=data.replace('local NO_GUI_ON_DEMAND = false','local NO_GUI_ON_DEMAND = true',1)
    if mode == 'userdata':
        assert data.count('local NO_GUI_USERDATA = false') == 1
        data=data.replace('local NO_GUI_USERDATA = false','local NO_GUI_USERDATA = true',1)
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
    result = dict(generation=generation, slots=None if on_demand else 1024,
                  mode='userdata' if mode == 'userdata' else ('demand' if on_demand else 'bounded'), intervalSeconds=1 if on_demand else 2,
                  installationSource='mod.io' if downloaded else 'local_or_other',
                  processRestartRequired=downloaded and mode != 'userdata',
                  idleConsumesSlots=not on_demand,
                  approximateLifetimeSeconds=None if on_demand else 2048,
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
