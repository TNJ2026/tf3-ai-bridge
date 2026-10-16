"""Audit a legacy pre-dispatch input refusal; --apply persists evidence, never replays."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server/src'))
from tf3_mcp.no_gui import NoGuiRequests


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--mod-content', type=Path, required=True)
    parser.add_argument('--receiver-source', type=Path, required=True)
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    host = NoGuiRequests(args.directory, args.mod_content)
    print(json.dumps(host.reconcile_legacy_input_rejection(args.request_id, args.receiver_source,
                                                          apply=args.apply), indent=2))
