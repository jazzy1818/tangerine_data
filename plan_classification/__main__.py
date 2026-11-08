"""CLI: inspect features, reproduce discovery, or select one plan module."""
import argparse
import json
from pathlib import Path

from . import FinancialConstraints, ShockScenario, build_case, get_customer_profile, select_plan
from .case import canonical_json
from .features import DATA_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    discovery = commands.add_parser('discover')
    discovery.add_argument('--output', type=Path, default=Path('reports/classification'))
    profile = commands.add_parser('profile')
    profile.add_argument('account_id', type=int)
    profile.add_argument('--as-of', help='YYYY-MM cutoff; excludes later history and loan snapshots.')
    classify = commands.add_parser('classify')
    classify.add_argument('account_id', type=int)
    classify.add_argument('--scenario', required=True, type=Path)
    classify.add_argument('--constraints', type=Path)
    classify.add_argument('--backend', choices=['rules','jev','jeff','gemini'], default='rules')
    classify.add_argument('--show-input', action='store_true', help='Print the canonical case without any API call.')
    classify.add_argument('--output', type=Path)
    for cmd in [discovery, profile, classify]:
        cmd.add_argument('--data-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    try:
        if args.command == 'discover':
            from .discovery import generate_report
            result = generate_report(args.data_dir, args.output)
            print(json.dumps(result, indent=2))
            return
        customer = get_customer_profile(args.account_id, args.data_dir, getattr(args,'as_of', None))
        if args.command == 'profile':
            print(customer.model_dump_json(indent=2))
            return
        scenario = ShockScenario.model_validate_json(args.scenario.read_text())
        constraints = FinancialConstraints.model_validate_json(args.constraints.read_text()) if args.constraints else None
        case = build_case(customer, scenario, constraints)
        result = canonical_json(case) if args.show_input else select_plan(case, args.backend).model_dump_json(indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result+'\n')
        print(result)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Classification input error: {exc}\n')


if __name__ == '__main__':
    main()
