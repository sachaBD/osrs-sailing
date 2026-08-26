"""port_tasks.list (wiki copy-paste) -> port_tasks.json + port_tasks.csv.

The pasted table carries a phantom empty column (the cargo icon cell), so each
row is: level, xp, notice board, cargo origin, destination, <blank>, cargo, qty, map.
"""
import csv, json

SRC, JSON_OUT, CSV_OUT = 'port_tasks.list', 'port_tasks.json', 'port_tasks.csv'


def parse(path=SRC):
    rows = []
    with open(path) as f:
        for i, parts in enumerate(csv.reader(f, delimiter='\t')):
            if i < 3 or len(parts) != 9:  # skip the 3 header lines and blank trailers
                continue
            level, xp, board, src, dst, _icon, cargo, qty, _map = (p.strip() for p in parts)
            xp_v = None if xp == 'Unknown' else int(xp.replace(',', ''))
            qty_v = int(qty)
            rows.append({
                'id': len(rows) + 1,
                'level': int(level),
                'xp': xp_v,
                'noticeBoard': board,
                'from': src,
                'to': dst,
                'cargo': cargo,
                'qty': qty_v,
                # every task either starts or ends at the board that advertises it
                'direction': 'outbound' if board == src else 'inbound',
                'xpPerQty': round(xp_v / qty_v, 1) if xp_v else None,
            })
    return rows


def main():
    rows = parse()
    json.dump(rows, open(JSON_OUT, 'w'), indent=1)
    with open(CSV_OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f'{len(rows)} tasks -> {JSON_OUT}, {CSV_OUT}')


if __name__ == '__main__':
    main()
