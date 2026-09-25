from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(\s?(?:%|percent\b))?")
_ISO_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_CATEGORY_TAG = re.compile(r"\((observed|computed|predicted)\)")


@dataclass(frozen=True)
class GroundingCheck:
    """Whether every number in an answer can be traced to a fact or to the
    question. `checked` counts the numbers found; `unsupported` lists the
    ones that matched nothing; `unknown_tags` lists category tags used
    that no fact carries."""

    verified: bool
    checked: int
    unsupported: tuple[str, ...]
    unknown_tags: tuple[str, ...]


def _date_parts(text: str) -> set[float]:
    parts: set[float] = set()
    for match in _ISO_DATETIME.finditer(text):
        try:
            moment = datetime.fromisoformat(match.group(0).replace("Z", "+00:00"))
        except ValueError:
            continue
        parts.update(
            {moment.year, moment.month, moment.day, moment.hour, moment.minute}
        )
    return parts


def _numbers_in_text(text: str) -> set[float]:
    return {float(match.group(1).replace(",", "")) for match in _NUMBER.finditer(text)}


def _collect(value: Any, into: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        into.add(float(value))
    elif isinstance(value, str):
        into.update(_numbers_in_text(value))
        into.update(_date_parts(value))
    elif isinstance(value, dict):
        for nested in value.values():
            _collect(nested, into)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _collect(nested, into)


def _decimals(token: str) -> int:
    return len(token.split(".", 1)[1]) if "." in token else 0


def _matches(stated: float, decimals: int, allowed: set[float]) -> bool:
    tolerance = 0.5 * 10 ** (-decimals) + 1e-12
    return any(abs(stated - candidate) <= tolerance for candidate in allowed)


def check_grounding(
    answer: str,
    facts: list[tuple[str, Any]],
    question: str = "",
) -> GroundingCheck:
    """`facts` is (category, payload) pairs. A stated number is supported
    when some fact or question number rounds to it at the precision it
    was written with; a percentage is also compared as a fraction, since
    probabilities are stored as fractions. Signs are ignored, so a
    negative SHAP contribution may be written with or without its minus."""
    allowed: set[float] = set()
    for _, payload in facts:
        _collect(payload, allowed)
    _collect(question, allowed)
    allowed = {abs(value) for value in allowed}

    unsupported: list[str] = []
    checked = 0
    for match in _NUMBER.finditer(answer):
        token = match.group(1)
        stated = float(token.replace(",", ""))
        decimals = _decimals(token)
        checked += 1

        supported = _matches(stated, decimals, allowed)
        if not supported and match.group(2):
            supported = _matches(stated / 100, decimals + 2, allowed)
        if not supported:
            unsupported.append(match.group(0).strip())

    categories = {category for category, _ in facts}
    unknown_tags = sorted(
        {tag for tag in _CATEGORY_TAG.findall(answer) if tag not in categories}
    )

    return GroundingCheck(
        verified=not unsupported and not unknown_tags,
        checked=checked,
        unsupported=tuple(unsupported),
        unknown_tags=tuple(unknown_tags),
    )
