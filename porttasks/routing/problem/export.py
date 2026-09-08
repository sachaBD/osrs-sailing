"""Write an `Instance` out as JSON, for the Rust search to read.

The search lives in `search/` and is a separate program, so the two halves
need one agreed file format. This is that seam, and it is deliberately dumb:
every array in `Instance`, flattened, with the names alongside. Nothing is
computed here that `instance.py` does not already compute, because the whole
point is that `tables/` stays the one source of truth and Rust never parses a
TSV.

    python3 -m porttasks.routing.problem.export 30 58 99
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from ...paths import DERIVED
from .instance import Instance

FORMAT = 2  # bump when a field changes shape; Rust checks it and refuses a mismatch


def path_for(level: int) -> Path:
    return DERIVED / f'instance_l{level}.json'


def as_dict(instance: Instance) -> dict:
    params = instance.params
    return {
        'format': FORMAT,
        'level': instance.level,
        'capacity': instance.capacity,
        'params': {
            'courier_per_board': params.courier_per_board,
            'reroll_completions': params.reroll_completions,
            't_board': params.t_board,
            't_drop': params.t_drop,
        },
        'ports': {
            'names': list(instance.port_names),
            'sail': [[int(v) for v in row] for row in instance.sail],
            'travel': [int(v) for v in instance.travel],
            'recall': [int(v) for v in instance.recall],
            'has_board': [bool(v) for v in instance.has_board],
        },
        'tasks': {
            'names': list(instance.task_names),
            'board': [int(v) for v in instance.task_board],
            'origin': [int(v) for v in instance.task_origin],
            'dest': [int(v) for v in instance.task_dest],
            'xp': [int(v) for v in instance.task_xp],
            'eligible': [bool(v) for v in instance.task_eligible],
        },
        'pools': {
            'ptr': [int(v) for v in instance.pool_ptr],
            'flat': [int(v) for v in instance.pool],
        },
    }


def write(level: int) -> Path:
    out = path_for(level)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(as_dict(Instance.at_level(level))))
    return out


def main(argv: list[str]) -> None:
    for level in [int(a) for a in argv] or [30, 60, 67, 99]:
        out = write(level)
        print(f'{out.relative_to(DERIVED.parent)}  {out.stat().st_size / 1024:.0f}K  '
              f'{Instance.at_level(level).describe()}')


if __name__ == '__main__':
    main(sys.argv[1:])
