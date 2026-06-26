"""Shared types for CML validation checks."""

import pandas as pd
from dataclasses import dataclass, field
from typing import Literal, Optional


Level = Literal["pass", "warn", "fail"]


@dataclass
class ValidationResult:
    check_name: str
    level: Level
    message: str
    failing_rows: Optional[pd.Index] = field(default=None)

    @property
    def passed(self) -> bool:
        return self.level == "pass"

    def __str__(self) -> str:
        tag = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[self.level]
        out = f"[{tag}] {self.check_name}: {self.message}"
        if self.level != "pass" and self.failing_rows is not None and len(self.failing_rows) > 0:
            out += f" (rows: {list(self.failing_rows[:10])}{'...' if len(self.failing_rows) > 10 else ''})"
        return out
