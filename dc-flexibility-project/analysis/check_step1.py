"""Validate the Step 1 document package; this does not validate research results."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import unquote
import argparse
import hashlib
import json
import re

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent


def check():
    errors = []
    parsed = {}
    for path in ROOT.rglob('*.json'):
        if '.git' in path.parts:
            continue
        try:
            parsed[path.relative_to(ROOT).as_posix()] = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            errors.append(f'JSON parse error: {path.relative_to(ROOT)}: {exc}')
    prefix = 'dc-flexibility-project/'
    d1 = parsed[prefix + 'planning/direction1/scenarios.draft.json']
    d3 = parsed[prefix + 'planning/direction3/05_initial_config.json']
    template = parsed[prefix + 'planning/data/initial_input.template.json']
    scenarios = d1['operational_scenarios']
    checks = {
        'direction1_has_12_unique_scenarios': len(scenarios) == 12 and len({s['id'] for s in scenarios}) == 12,
        'direction1_has_2_management_philosophies': len(d1['management_philosophies']) == 2,
        'direction1_run_disabled': d1['execution_enabled'] is False,
        'direction3_run_disabled': d3['run_enabled'] is False and d3['run_has_occurred'] is False,
        'direction3_no_new_task_controls': all(d3['study_boundary'][key] is False for key in ['new_task_migration_allowed', 'new_task_deferral_allowed', 'new_execution_control_allowed']),
        '12_empty_input_tables': len(template['tables']) == 12 and all(t['records'] == [] for t in template['tables'].values()),
        'obsolete_active_csvs_removed': not (PROJECT/'planning/task-tracker.csv').exists() and not (PROJECT/'planning/data-dictionary-template.csv').exists(),
        'misnamed_manifest_removed': not (PROJECT/'sources/download-manifest.txt').exists(),
    }
    import_manifest = parsed[prefix + 'sources/local-documents/import-manifest.json']
    source_hashes = []
    for record in import_manifest['documents']:
        path = ROOT / record['repository_relative_path']
        raw = path.read_bytes()
        match = len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256']
        source_hashes.append(match)
        if not match:
            errors.append('Original source hash mismatch: ' + record['repository_relative_path'])
    checks['eight_original_documents_preserved'] = len(source_hashes) == 8 and all(source_hashes)

    # Historical sources retain original local references. Only current authored entry points are gated.
    selected = [ROOT/'README.md', PROJECT/'README.md', PROJECT/'CONTRIBUTING.md']
    selected += [p for p in (PROJECT/'planning').rglob('*.md') if 'archive' not in p.parts]
    selected += list((PROJECT/'papers').rglob('*.md'))
    selected += [PROJECT/'data/metadata/step1-data-readiness.md']
    selected += list((PROJECT/'data/metadata/public-seed').glob('*.md'))
    selected += [PROJECT/'meeting-notes/2026-10-19-step1-decisions.md']
    link_count = 0
    for path in selected:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = unquote(target.strip().strip('<>')).split('#')[0]
            if not target or re.match(r'^(https?://|mailto:)', target):
                continue
            link_count += 1
            if not (path.parent / target).exists():
                errors.append(f'Broken current link: {path.relative_to(ROOT)} -> {target}')
    for name, passed in checks.items():
        if not passed:
            errors.append('Failed check: ' + name)
    return {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Document links, JSON syntax, design configuration, empty templates and original document hashes; no model execution or research-result validation.',
        'checks': checks,
        'current_relative_links_checked': link_count,
        'json_files_checked': len(parsed),
        'historical_source_local_links_excluded': True,
        'errors': errors,
        'result': 'passed' if not errors else 'failed',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-report', action='store_true', help='Save the package check in data/metadata/step1-validation.json')
    args = parser.parse_args()
    report = check()
    if args.write_report:
        (PROJECT/'data/metadata/step1-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['result'] == 'passed' else 1)
