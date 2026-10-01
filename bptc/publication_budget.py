"""Prospective, fail-closed accounting for scientific obligations."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import Lock
from typing import Dict


class BudgetExceeded(RuntimeError):
    """Raised before an operation that would exceed the declared budget."""


@dataclass
class ObligationLedger:
    limit: int
    used: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit <= 0:
            raise ValueError("limit must be a positive integer")
        if type(self.used) is not int or self.used < 0 or self.used > self.limit:
            raise ValueError("invalid initial use")
        if any((type(v) is not int or v < 0) for v in self.categories.values()):
            raise ValueError("invalid category count")
        if sum(self.categories.values()) != self.used:
            raise ValueError("category counts must sum to used")

    def charge(self, category: str, count: int = 1) -> None:
        """Atomically reserve *count* obligations before their execution."""
        if type(category) is not str or not category:
            raise ValueError("category must be a non-empty string")
        if type(count) is not int or count <= 0:
            raise ValueError("count must be a positive integer")
        with self._lock:
            if self.used + count > self.limit:
                raise BudgetExceeded(
                    f"budget {self.limit} would be exceeded by {category}:{count}; "
                    f"currently used {self.used}"
                )
            self.used += count
            self.categories[category] = self.categories.get(category, 0) + count

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def to_dict(self) -> dict:
        return {
            "format": "bptc-obligation-ledger-v1",
            "limit": self.limit,
            "events_used": self.used,
            "remaining": self.remaining,
            "categories": dict(sorted(self.categories.items())),
            "status": "within-limit" if self.used <= self.limit else "over-limit",
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
