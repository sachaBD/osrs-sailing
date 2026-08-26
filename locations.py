"""Read/write locations.tsv, the hand-editable port reference table.

Every column is yours to edit; refresh_wiki.py only fills blanks unless forced.
"""
from __future__ import annotations

FIELDS = ['name', 'region', 'subregion', 'oceans', 'dock_level', 'shipwright',
          'notice_board', 'salvaging', 'ledger', 'crew_registrar', 'requirements', 'coords']
LIST_FIELDS = {'oceans'}
PATH = 'locations.tsv'

Port = dict[str, object]


class LocationsError(Exception):
    """The file on disk does not match the expected schema."""


def _data_lines(path: str) -> list[str]:
    with open(path) as f:
        return [line.rstrip('\n') for line in f if line.strip() and not line.startswith('#')]


def load(path: str = PATH) -> dict[str, Port]:
    """-> {name: {field: value}}, with `oceans` as a list."""
    lines = _data_lines(path)
    if not lines:
        raise LocationsError(f'{path} has no rows')

    header = lines[0].split('\t')
    if header != FIELDS:
        raise LocationsError(
            f'unexpected header in {path}\n  found:    {header}\n  expected: {FIELDS}')

    ports: dict[str, Port] = {}
    for line in lines[1:]:
        cells = (line.split('\t') + [''] * len(FIELDS))[:len(FIELDS)]
        record = {field: cell.strip() for field, cell in zip(FIELDS, cells)}
        name = record.pop('name')
        if not name:
            raise LocationsError(f'{path} has a row with no name: {line!r}')
        for field in LIST_FIELDS:
            record[field] = [v.strip() for v in record[field].split('|') if v.strip()]
        record['region'] = record['region'] or 'Unknown'
        record['subregion'] = record['subregion'] or None
        ports[name] = record
    return ports


def save(ports: dict[str, Port], path: str = PATH) -> None:
    """Rewrite the data rows, preserving the comment header at the top."""
    head: list[str] = []
    with open(path) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                head.append(line.rstrip('\n'))
            else:
                break

    lines = head + ['\t'.join(FIELDS)]
    for name, port in sorted(ports.items()):
        cells = [name]
        for field in FIELDS[1:]:
            value = port.get(field) or ''
            cells.append('|'.join(value) if field in LIST_FIELDS else str(value))
        lines.append('\t'.join(cells))
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
