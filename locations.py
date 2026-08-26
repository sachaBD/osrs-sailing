"""Read/write locations.tsv, the hand-editable port reference table.

Every column is yours to edit; refresh_wiki.py only fills blanks unless forced.
"""
FIELDS = ['name', 'region', 'subregion', 'oceans', 'dock_level', 'shipwright',
          'notice_board', 'salvaging', 'ledger', 'crew_registrar', 'requirements', 'coords']
LIST_FIELDS = {'oceans'}
PATH = 'locations.tsv'


def load(path=PATH):
    """-> {name: {field: value}}, with `oceans` as a list."""
    with open(path) as f:
        lines = [l.rstrip('\n') for l in f if l.strip() and not l.startswith('#')]
    header = lines[0].split('\t')
    assert header == FIELDS, f'unexpected header in {path}:\n  {header}\n  {FIELDS}'
    out = {}
    for line in lines[1:]:
        cells = (line.split('\t') + [''] * len(FIELDS))[:len(FIELDS)]
        rec = {f: c.strip() for f, c in zip(FIELDS, cells)}
        name = rec.pop('name')
        for f in LIST_FIELDS:
            rec[f] = [v.strip() for v in rec[f].split('|') if v.strip()]
        rec['region'] = rec['region'] or 'Unknown'
        rec['subregion'] = rec['subregion'] or None
        out[name] = rec
    return out


def save(meta, path=PATH):
    """Rewrite data rows, preserving the comment header at the top of the file."""
    head = []
    with open(path) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                head.append(line.rstrip('\n'))
            else:
                break
    lines = head + ['\t'.join(FIELDS)]
    for name, v in sorted(meta.items()):
        cells = [name]
        for f in FIELDS[1:]:
            val = v.get(f) or ''
            cells.append('|'.join(val) if f in LIST_FIELDS else str(val))
        lines.append('\t'.join(cells))
    open(path, 'w').write('\n'.join(lines) + '\n')
