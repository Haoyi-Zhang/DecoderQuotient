"""Hard, process-local obligation budgeting for bounded scientific runs.

The budget is deliberately small and auditable.  A reservation is validated and
committed atomically before the corresponding operation is allowed to proceed.
Rejected reservations leave the counter state unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable, Iterator, Mapping


class BudgetError(RuntimeError):
    """Base class for budget and metering errors."""


class BudgetExceeded(BudgetError):
    """Raised before an operation whose reservation would exceed the limit."""

    def __init__(self, *, limit: int, used: int, requested: int, category: str):
        self.limit = limit
        self.used = used
        self.requested = requested
        self.category = category
        super().__init__(
            f"obligation budget exceeded: used={used}, requested={requested}, "
            f"limit={limit}, category={category!r}"
        )


class MeterInactive(BudgetError):
    """Raised when a scientific entry point is invoked outside the hard meter."""


@dataclass
class ObligationBudget:
    """Thread-safe monotone counter with atomic category reservations."""

    limit: int
    label: str = "scientific-obligations"
    _used: int = 0
    _categories: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def __post_init__(self) -> None:
        self.limit = _positive_int(self.limit, "limit")
        if not isinstance(self.label, str) or not self.label.strip():
            raise TypeError("label must be a nonempty string")

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return self.limit - self._used

    def reserve(self, category: str, count: int = 1) -> int:
        """Atomically reserve ``count`` obligations and return the new total."""
        category = _category(category)
        count = _positive_int(count, "count")
        with self._lock:
            if self._used + count > self.limit:
                raise BudgetExceeded(
                    limit=self.limit,
                    used=self._used,
                    requested=count,
                    category=category,
                )
            self._used += count
            self._categories[category] = self._categories.get(category, 0) + count
            return self._used

    def reserve_many(self, reservations: Mapping[str, int] | Iterable[tuple[str, int]]) -> int:
        """Atomically reserve a batch; no item is committed if the batch fails."""
        items = list(reservations.items() if isinstance(reservations, Mapping) else reservations)
        if not items:
            raise ValueError("reservations must not be empty")
        normalized: list[tuple[str, int]] = [
            (_category(category), _positive_int(count, "count"))
            for category, count in items
        ]
        requested = sum(count for _, count in normalized)
        with self._lock:
            if self._used + requested > self.limit:
                labels = ",".join(category for category, _ in normalized)
                raise BudgetExceeded(
                    limit=self.limit,
                    used=self._used,
                    requested=requested,
                    category=labels,
                )
            for category, count in normalized:
                self._categories[category] = self._categories.get(category, 0) + count
            self._used += requested
            return self._used

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            categories = dict(sorted(self._categories.items()))
            return {
                "label": self.label,
                "limit": self.limit,
                "used": self._used,
                "remaining": self.limit - self._used,
                "categories": categories,
                "category_sum": sum(categories.values()),
            }


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _category(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("category must be a nonempty string")
    return value.strip()


_ACTIVE_BUDGET: ContextVar[ObligationBudget | None] = ContextVar(
    "bptc_active_obligation_budget", default=None
)
_HARD_METER_ACTIVE: ContextVar[bool] = ContextVar(
    "bptc_hard_meter_active", default=False
)


@contextmanager
def activate_hard_meter(budget: ObligationBudget) -> Iterator[ObligationBudget]:
    """Activate ``budget`` for one hard-metered execution context."""
    if not isinstance(budget, ObligationBudget):
        raise TypeError("budget must be an ObligationBudget")
    token_budget = _ACTIVE_BUDGET.set(budget)
    token_meter = _HARD_METER_ACTIVE.set(True)
    try:
        yield budget
    finally:
        _HARD_METER_ACTIVE.reset(token_meter)
        _ACTIVE_BUDGET.reset(token_budget)


def require_hard_meter() -> ObligationBudget:
    """Return the active budget or reject an unmetered scientific invocation."""
    budget = _ACTIVE_BUDGET.get()
    if budget is None or not _HARD_METER_ACTIVE.get():
        raise MeterInactive(
            "scientific entry point requires `python -m bptc.metered_runner ...`"
        )
    return budget
