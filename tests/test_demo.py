"""The first-demonstration script runs end to end."""

from __future__ import annotations

import demo


def test_demo_runs(capsys):
    assert demo.run_demo(iterations=400, seed=1) == 0
    output = capsys.readouterr().out
    for expected in (
        "FIRST DEMONSTRATION",
        "Build A — Jackie x2",
        "Build B — Jackie x3",
        "MULLIGAN POLICIES",
        "WHAT THE THIRD JACKIE COSTS AND BUYS",
        "HONEST LIMITS OF THIS DEMONSTRATION",
        "EXACT — Hypergeometric",
    ):
        assert expected in output
