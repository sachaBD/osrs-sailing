"""The search space: `docs/PROBLEM.md` made executable.

Ground truth (`../world`) plus what it costs, flattened into the SMDP that
every policy is measured against.

    params.py     what things cost. Mostly guesses; `make sim-sweep` is why
    instance.py   world + params -> arrays at a level: names in, arrays out
    sim.py        the dynamics those arrays define; integer ticks only

This is the component that has to be *right* rather than good - a wrong
simulator invalidates everything above it.
"""
