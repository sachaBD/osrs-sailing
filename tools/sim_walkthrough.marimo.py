"""One state, one action, the state that follows.

The simulator is the component that has to be *right* - everything above it is
measured against it - so this notebook does nothing clever. It builds a state,
shows it as the agent sees it, lets you pick one legal action, and shows what
that action did. Then it checks the two properties the search layer will lean
on: that a state survives a round trip through JSON, and that stepping a state
never disturbs the one it came from.

Run: marimo edit tools/sim_walkthrough.marimo.py
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from porttasks.routing.problem.instance import Instance
    from porttasks.routing.problem.sim import Sim
    return Instance, Sim, mo


@app.cell
def _(mo):
    mo.md("# The port-task SMDP, one step at a time")
    return


@app.cell
def _(mo):
    level = mo.ui.slider(20, 76, value=30, step=1, label="Sailing level")
    seed = mo.ui.slider(0, 20, value=0, step=1, label="Seed (names the board draws)")
    mo.hstack([level, seed], justify="start", gap=2)
    return level, seed


@app.cell
def _(Instance, Sim, level, seed):
    instance = Instance.at_level(level.value)
    sim = Sim(instance)
    start = sim.reset(seed=seed.value)
    return instance, sim, start


@app.cell
def _(instance, mo):
    mo.md(f"`{instance.describe()}`")
    return


@app.cell
def _(mo, sim, start):
    mo.md(f"## The state\n\n```\n{sim.describe(start)}\n```")
    return


@app.cell
def _(instance, mo, sim, start):
    legal = sim.legal(start)
    options = {f"{i:>3}  {a.describe(instance)}": a for i, a in enumerate(legal)}
    choice = mo.ui.dropdown(options, value=next(iter(options)),
                            label=f"Action ({len(legal)} legal)")
    choice
    return choice, legal, options


@app.cell
def _(choice, mo, sim, start):
    step = sim.step(start, choice.value)
    mo.md(
        f"## After `{choice.value.describe(sim.instance)}`\n\n"
        f"**+{step.xp:,} xp** for **{step.ticks} ticks**\n\n"
        f"```\n{sim.describe(step.state)}\n```")
    return (step,)


@app.cell
def _(mo):
    mo.md(
        """
        ## The two properties search needs

        A state is a value: it serialises to scalars and short lists, and
        stepping it returns a new one rather than editing it in place. Both are
        asserted below, so this cell failing is a real regression.
        """)
    return


@app.cell
def _(Sim, instance, mo, sim, start, step):
    text = sim.to_json(step.state)
    _, restored = Sim.from_json(text, instance)
    assert restored == step.state, "a state did not survive a JSON round trip"
    assert sim.describe(restored) == sim.describe(step.state)
    assert start == sim.reset(seed=start.seed), "stepping mutated the state it came from"

    mo.md(f"Round trip over **{len(text)} bytes** of JSON:\n\n```json\n{text}\n```")
    return


@app.cell
def _(mo, sim, start):
    _state, _lines = start, []
    for _ in range(12):
        _action = sim.legal(_state)[0]
        _step = sim.step(_state, _action)
        _lines.append(f"{_state.ticks:>6}  {_action.describe(sim.instance):<52}"
                      f"  +{_step.xp:,} xp")
        _state = _step.state

    mo.md("## Twelve steps of the dullest policy there is (always the first legal action)\n\n"
          "```\n" + "\n".join(_lines) + "\n```")
    return
