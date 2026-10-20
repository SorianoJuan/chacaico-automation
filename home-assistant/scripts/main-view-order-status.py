#!/usr/bin/env python3
"""Add valve-specific command status immediately after each valve in the main view."""
import argparse
import copy
import json
from pathlib import Path


def merge(document, nodes=(1, 2)):
    result = copy.deepcopy(document)
    if result.get('key') != 'lovelace.dashboard_chacaico':
        raise ValueError('Unexpected dashboard')
    main = result['data']['config']['views'][0]
    if main.get('path') == 'configuracion-lora':
        raise ValueError('The first view must be the main valve view')
    counts = {n: 0 for n in nodes}
    def visit(value):
        if isinstance(value, dict):
            rows = value.get('entities')
            if isinstance(rows, list):
                for n in nodes:
                    targets = {f'valve.chacaico_node_{n}', f'switch.chacaico_node_{n}_valve'}
                    entity = f'sensor.chacaico_node_{n}_valve_command_status'
                    def ident(row):
                        return row.get('entity') if isinstance(row, dict) else row
                    if any(ident(row) in targets for row in rows):
                        rows = [row for row in rows if ident(row) != entity]
                        for i, row in enumerate(rows):
                            if ident(row) in targets:
                                rows.insert(i+1, {'entity': entity, 'name': 'Orden de válvula'})
                                counts[n] += 1
                                break
                value['entities'] = rows
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(main)
    if any(count != 1 for count in counts.values()):
        raise ValueError(f'Expected one control per node in main view: {counts}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(merge(json.loads(args.storage.read_text())), ensure_ascii=False, indent=2)+'\n')
