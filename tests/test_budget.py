#!/usr/bin/env python3
"""Unit tests for hard obligation budgeting (no scientific execution)."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from bptc.budget import BudgetExceeded, MeterInactive, ObligationBudget, require_hard_meter
from bptc.focused import run as focused_run


def expect(exc_type, fn) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def main() -> None:
    budget = ObligationBudget(3, label="unit")
    assert budget.reserve("a", 2) == 2
    before = budget.snapshot()
    expect(BudgetExceeded, lambda: budget.reserve("b", 2))
    assert budget.snapshot() == before
    assert budget.reserve("b") == 3
    assert budget.snapshot()["category_sum"] == 3

    batch = ObligationBudget(5)
    assert batch.reserve_many([("x", 2), ("y", 3)]) == 5
    before = batch.snapshot()
    expect(BudgetExceeded, lambda: batch.reserve_many({"z": 1}))
    assert batch.snapshot() == before

    for bad in (True, False, 0, -1, 1.5, "1"):
        expect((TypeError, ValueError), lambda bad=bad: ObligationBudget(3).reserve("x", bad))
    expect(TypeError, lambda: ObligationBudget(True))
    expect(TypeError, lambda: ObligationBudget(3).reserve(""))

    concurrent = ObligationBudget(1000)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(100):
                concurrent.reserve("thread")
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert concurrent.used == 1000

    expect(MeterInactive, require_hard_meter)
    with tempfile.TemporaryDirectory() as tmp:
        expect(MeterInactive, lambda: focused_run(Path(tmp) / "should-not-exist.json"))

    print(json.dumps({"passed": True, "tests": 12, "concurrent_reservations": concurrent.used}, sort_keys=True))


if __name__ == "__main__":
    main()
