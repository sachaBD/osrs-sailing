"""Refresh port facts in tables/locations.tsv from the OSRS wiki's ocean dock tables.

Pulls, per docking point: which ocean it's in, the Sailing level to dock, any
other requirement, which amenities it has (shipwright = boat recovery), and its
world coordinates.

Non-destructive by default: fills blanks and reports differences, but leaves
values you edited by hand alone. Pass --apply to take the wiki's version.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

from .tables import locations
from .tiles import grid

OCEANS = ['Ardent Ocean', 'Unquiet Ocean', 'Eastern Ocean', 'Shrouded Ocean', 'Western Ocean',
          'Northern Ocean', 'Untamed Ocean', 'Forgotten Ocean', 'Sunset Ocean']
UA = {'User-Agent': 'osrs-port-tasks-local/0.1'}

# wiki table header -> tables/locations.tsv column
COLUMNS = {
    'Level': 'dock_level',        # header renders as "{{SCP|Sailing}} Level"
    'Other requirements': 'requirements',
    'Shipwright': 'shipwright',
    'Notice board': 'notice_board',
    'Salvaging station': 'salvaging',
    'Ledger table': 'ledger',
    'Crew Registrar': 'crew_registrar',
}
YESNO = {'okay': 'yes', 'not okay': 'no', 'na': '', 'n/a': ''}


def _wikitext(page):
    url = 'https://oldschool.runescape.wiki/api.php?' + urllib.parse.urlencode(
        {'action': 'parse', 'format': 'json', 'page': page, 'prop': 'wikitext'})
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    return json.load(r)['parse']['wikitext']['*']


def _clean(cell):
    """Strip wiki markup down to a plain value."""
    cell = cell.strip().strip('|').strip()
    tmpl = re.fullmatch(r'\{\{([^|}]+)\}\}', cell)
    if tmpl:
        return YESNO.get(tmpl.group(1).strip().lower(), tmpl.group(1).strip())
    cell = re.sub(r'\[\[[^\]|]*\|([^\]]*)\]\]', r'\1', cell)   # [[a|b]] -> b
    cell = re.sub(r'\[\[([^\]]*)\]\]', r'\1', cell)            # [[a]]   -> a
    cell = re.sub(r'\{\{SCP\|([^|}]+)\|(\d+)\}\}', r'\2 \1', cell)
    cell = re.sub(r'\{\{[^}]*\}\}', '', cell)
    return re.sub(r'\s+', ' ', cell).strip()


def parse_ocean(page):
    """-> {dock name: {column: value}} for one ocean page."""
    wt = _wikitext(page)
    sec = re.search(r'==\s*Docking points\s*==(.*?)(?=\n==[^=]|\Z)', wt, re.S)
    if not sec:
        return {}
    tbl = re.search(r'\{\|(.*?)\n\|\}', sec.group(1), re.S)
    if not tbl:
        return {}
    tbl = tbl.group(1)

    headers = [_clean(re.sub(r'^.*?\|', '', h) if 'colspan' in h else h)
               for h in re.findall(r'^!\s*(.+)$', tbl, re.M)]

    out = {}
    for row in tbl.split('\n|-')[1:]:
        cells = [c for c in row.split('\n|')[1:]]
        if not cells:
            continue
        name = re.match(r'\s*\{\{ilinkt\|([^|}]+)', cells[0])
        if not name:
            continue
        rec = {'oceans': [page]}
        for header, cell in zip(headers[1:], cells[1:]):
            if header == 'Map':
                coords = re.search(r'\|(\d{3,5}),(\d{3,5})', cell)
                if coords:
                    rec['coords'] = f'{coords.group(1)},{coords.group(2)}'
            elif header in COLUMNS:
                rec[COLUMNS[header]] = _clean(cell)
        out[name.group(1).strip()] = rec
    return out


def refresh_tile_version():
    """The wiki re-renders its maps periodically, which changes the version in
    every tile URL. Scrape the current one off a page that embeds a map."""
    url = 'https://oldschool.runescape.wiki/w/Ardent_Ocean'
    html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    found = set(re.findall(r'maps\.runescape\.wiki/osrs/versions/([^/]+)/', html.read().decode('utf-8', 'replace')))
    if not found:
        print('  ?  tile version: none found on the page, leaving tables/map_config.json alone')
        return
    latest = sorted(found)[-1]
    cfg = grid.config()
    if cfg['tile_version'] == latest:
        print(f'  =  tile version: {latest} (unchanged)')
        return
    print(f'  ~  tile version: {cfg["tile_version"]} -> {latest}; '
          f'run `make clean-tiles && make tiles` to re-download')
    cfg['tile_version'] = latest
    json.dump(cfg, open(grid.CONFIG, 'w'), indent=2)


def main():
    apply_changes = '--apply' in sys.argv
    refresh_tile_version()
    meta = locations.load()

    wiki = {}
    for o in OCEANS:
        for dock, rec in parse_ocean(o).items():
            if dock in wiki:
                wiki[dock]['oceans'] += rec['oceans']
            else:
                wiki[dock] = rec

    filled = diffs = 0
    for name, local in sorted(meta.items()):
        remote = wiki.get(name)
        if not remote:
            print(f'  ?  {name}: no dock table entry (local values kept)')
            continue
        for field, new in remote.items():
            if new in ('', None, []):
                continue
            old = local.get(field)
            same = sorted(old) == sorted(new) if field == 'oceans' else old == new
            if not old:
                local[field] = new
                filled += 1
                print(f'  +  {name}.{field} = {new}')
            elif not same:
                diffs += 1
                print(f'  ~  {name}.{field}: local {old!r} vs wiki {new!r} '
                      f'[{"updated" if apply_changes else "kept local"}]')
                if apply_changes:
                    local[field] = new

    if filled or (diffs and apply_changes):
        locations.save(meta)
        print(f'wrote {locations.PATH}')
    else:
        print('no changes written' + ('' if apply_changes else '; use --apply to take wiki values'))
    print(f'{filled} filled, {diffs} differing')


if __name__ == '__main__':
    main()
