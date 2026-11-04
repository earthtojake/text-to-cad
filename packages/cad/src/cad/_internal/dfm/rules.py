"""Rule sets: what a manufacturing check compares its measurements against, each rule cited.

A check's measurements are facts (``cad.build123d``'s and ``cad.trimesh``'s reports). A **rule set** turns
them into verdicts: a named, versioned table of rules, each a limit on one measured field, taken from one
source -- a shop's published design guide (Protolabs, Protolabs Network (Hubs), Xometry, SendCutSend) or
text-to-cad's own ``generic`` set, a starting point that is no shop's and says so in every verdict. A rule
never changes a measurement and a verdict never replaces one: the report carries both.

A rule reads ``report[family]``: a family's ``items`` (one record per feature, each with its ``location`` --
a ref in ``cad xbf inspect``'s grammar -- and ``xyz``), or the family itself where it has none (one figure
for the whole part). The limit is a number, or one number per value of a ``context`` key (``by``: the
material's class, a printing technology), times another (``scale_by``: a sheet's thickness), and the rule
applies only where the context matches ``when`` (elsewhere it is recorded ``not_applicable``, never dropped)
and to the items matching ``item_when`` (``not_applicable`` too where no item carries the fields it reads: a
mesh's walls, against a rule for supported walls). A family measured with nothing to judge -- no hole, no
wall under its threshold -- passes, ``none found``. A figure that was not measured, or a family that was
not, is no verdict: it is counted (``not_evaluated``), never passed.

The standard library alone: the command resolves a rule set before it starts an environment.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cad.results import CheckFinding

__all__ = ["Rule", "RuleSet", "Source", "evaluate"]

#: Verdicts a rule writes as findings, at most, before the rest are counted in one more.
SHOWN_PER_RULE = 8


@dataclass(frozen=True)
class Source:
    """Where a rule's number comes from: the publisher's page, as read on ``accessed``."""

    id: str
    publisher: str
    title: str
    url: str
    accessed: str

    def as_data(self) -> dict[str, str]:
        return {"id": self.id, "publisher": self.publisher, "title": self.title, "url": self.url,
                "accessed": self.accessed}


@dataclass(frozen=True)
class Rule:
    """One limit on one measured field (see the module)."""

    id: str                     # stable, the finding's code: "cnc.internal_corner_radius"
    family: str                 # the report's key: "pockets"
    field: str                  # the item's (or the family's) figure: "corner_radius_mm"
    op: str                     # "min": the figure is at least the limit; "max": at most
    limit: float | Mapping[str, float]
    unit: str                   # "mm", "deg", "ratio", "mm2", "%"
    what: str                   # the figure in words, for the message: "internal corner radius"
    source: str                 # a Source's id
    severity: str = "error"     # "error": not made as drawn; "warning": cost, risk or a shop's preference
    by: str | None = None       # the context key choosing the limit from a mapping
    scale_by: str | None = None  # the context key the limit is multiplied by
    when: Mapping[str, Any] = field(default_factory=dict)       # context key: value or tuple of values
    item_when: Mapping[str, Any] = field(default_factory=dict)  # item field: value or tuple of values
    fix: str = ""               # what to change, formatted with value, limit, unit
    note: str = ""              # the source's own framing, paraphrased

    def __post_init__(self) -> None:
        if self.op not in ("min", "max"):
            raise ValueError(f"rule {self.id}: op is min or max, not {self.op!r}")
        if self.severity not in ("error", "warning"):
            raise ValueError(f"rule {self.id}: severity is error or warning, not {self.severity!r}")
        if isinstance(self.limit, Mapping) and self.by is None:
            raise ValueError(f"rule {self.id}: a limit per value needs the context key it is chosen by (by=)")

    def limit_for(self, context: Mapping[str, Any]) -> float | None:
        """The limit in this context, or None where the rule gives none for it."""
        limit = self.limit
        if isinstance(limit, Mapping):
            key = context.get(self.by) if self.by else None
            limit = limit.get(str(key)) if key is not None else None
            if limit is None:
                return None
        value = float(limit)
        if self.scale_by is not None:
            scale = context.get(self.scale_by)
            if not isinstance(scale, (int, float)) or not math.isfinite(scale):
                return None
            value *= float(scale)
        return value

    def applies(self, context: Mapping[str, Any]) -> bool:
        return _matches(self.when, context)


@dataclass(frozen=True)
class RuleSet:
    """A named, versioned table of rules for one process, and the sources they cite."""

    name: str                   # "generic", "protolabs", "hubs", "xometry", "sendcutsend"
    process: str
    title: str                  # "text-to-cad generic", "Protolabs"
    version: str                # the table's own version: "2026-11-03"
    rules: tuple[Rule, ...]
    sources: tuple[Source, ...]
    generic: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        known = {source.id for source in self.sources}
        for rule in self.rules:
            if rule.source not in known:
                raise ValueError(f"rule set {self.name}: rule {rule.id} cites {rule.source!r}, which it does not list")

    def source(self, ident: str) -> Source:
        return next(source for source in self.sources if source.id == ident)


def _matches(conditions: Mapping[str, Any], values: Mapping[str, Any]) -> bool:
    for key, wanted in conditions.items():
        have = values.get(key)
        if isinstance(wanted, (tuple, list, set, frozenset)):
            if have not in wanted:
                return False
        elif have != wanted:
            return False
    return True


def _wants_none(wanted: Any) -> bool:
    return wanted is None or (isinstance(wanted, (tuple, list, set, frozenset)) and None in wanted)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _fails(rule: Rule, value: float, limit: float) -> bool:
    slack = 1e-9 * max(1.0, abs(limit))
    return value < limit - slack if rule.op == "min" else value > limit + slack


def _items(report: Mapping[str, Any], rule: Rule) -> tuple[list[Mapping[str, Any]] | None, bool]:
    """The items the rule judges (None: the family was not measured), and whether the family holds items the
    rule could read at all: False where every item lacks the fields its ``item_when`` reads (a mesh's walls,
    which do not say whether they are supported, against a rule for supported walls)."""
    family = report.get(rule.family)
    if not isinstance(family, Mapping) or "error" in family:
        return None, True
    items = family.get("items")
    if isinstance(items, list):
        listed = [item for item in items if isinstance(item, Mapping)]
        readable = not rule.item_when or not listed or any(
            all(item.get(key) is not None or _wants_none(wanted) for key, wanted in rule.item_when.items())
            for item in listed)
        return [item for item in listed if _matches(rule.item_when, item)], readable
    return [family], True


def _where(item: Mapping[str, Any], rule: Rule) -> str:
    location = item.get("location")
    if location:
        return str(location)
    xyz = item.get("xyz")
    if xyz:
        return ", ".join(f"{float(value):g}" for value in xyz)
    return rule.family


def _message(rule: Rule, rule_set: RuleSet, value: float, limit: float) -> str:
    relation = "under" if rule.op == "min" else "over"
    bound = "minimum" if rule.op == "min" else "maximum"
    source = rule_set.source(rule.source)
    origin = (f"{rule_set.title}'s generic rule, no shop's" if rule_set.generic
              else f"{source.publisher}, {source.title}")
    return f"{rule.what} {value:.4g} {rule.unit} is {relation} the {limit:.4g} {rule.unit} {bound} ({origin})"


def _hint(rule: Rule, value: float, limit: float) -> str | None:
    if not rule.fix:
        return None
    try:
        return rule.fix.format(value=value, limit=limit, unit=rule.unit)
    except (KeyError, IndexError, ValueError):
        return rule.fix


def evaluate(report: Mapping[str, Any], rule_set: RuleSet,
             context: Mapping[str, Any]) -> tuple[list[CheckFinding], dict[str, Any]]:
    """The verdicts of ``rule_set`` on ``report`` in ``context``: findings (one per failing item, at most
    ``SHOWN_PER_RULE`` per rule, the rest counted in one more) and the record the report keeps of them
    (``measurements["rules"]``: the set, every rule's outcome, every failure's value, limit and place)."""
    findings: list[CheckFinding] = []
    outcomes: list[dict[str, Any]] = []
    for rule in rule_set.rules:
        if not rule.applies(context):
            # Recorded, never dropped: a rule that does not apply here is not a pass either.
            outcomes.append({"rule": rule.id, "family": rule.family, "field": rule.field, "op": rule.op,
                             "unit": rule.unit, "severity": rule.severity, "source": rule.source,
                             "status": "not_applicable", "reason": "applies only where " + ", ".join(
                                 f"{key} is {value}" for key, value in rule.when.items())})
            continue
        limit = rule.limit_for(context)
        items, readable = _items(report, rule) if limit is not None else (None, True)
        outcome: dict[str, Any] = {"rule": rule.id, "family": rule.family, "field": rule.field, "op": rule.op,
                                   "limit": limit, "unit": rule.unit, "severity": rule.severity,
                                   "source": rule.source}
        if limit is None or items is None:
            outcome["status"] = "not_evaluated"
            outcome["reason"] = ("the rule set gives no limit here" if limit is None
                                 else f"{rule.family} was not measured")
            outcomes.append(outcome)
            continue
        if not readable:
            outcome.update(status="not_applicable", reason="this source's " + rule.family + " do not say "
                           + ", ".join(rule.item_when) + ": another rule judges them")
            outcomes.append(outcome)
            continue
        failures: list[dict[str, Any]] = []
        evaluated = unmeasured = 0
        for item in items:
            value = _number(item.get(rule.field))
            if value is None:
                unmeasured += 1
                continue
            evaluated += 1
            if _fails(rule, value, limit):
                failures.append({"value": value, "location": _where(item, rule), "xyz": item.get("xyz")})
        failures.sort(key=lambda found: found["value"], reverse=rule.op == "max")
        # Measured and nothing to judge -- no hole, no wall under the family's own threshold -- is a pass: none
        # found. A figure the items do not carry is no pass.
        status = "failed" if failures else "passed" if evaluated or not unmeasured else "not_evaluated"
        outcome.update(status=status, evaluated=evaluated, unmeasured=unmeasured, failures=failures)
        if not evaluated and not failures:
            outcome["reason"] = "none found: no feature it applies to" if not unmeasured else \
                f"{rule.field} was not measured"
        outcomes.append(outcome)
        for failure in failures[:SHOWN_PER_RULE]:
            findings.append(CheckFinding(rule.severity, rule.id, _message(rule, rule_set, failure["value"], limit),
                                         failure["location"], _hint(rule, failure["value"], limit)))
        if len(failures) > SHOWN_PER_RULE:
            findings.append(CheckFinding(rule.severity, rule.id,
                                         f"{len(failures) - SHOWN_PER_RULE} more of the same "
                                         f"(measurements.rules lists every one)", rule.family))
    record = {
        "set": rule_set.name, "title": rule_set.title, "version": rule_set.version, "generic": rule_set.generic,
        "note": rule_set.note, "context": {key: value for key, value in context.items() if _plain(value)},
        "evaluated": sum(1 for outcome in outcomes if outcome["status"] in ("passed", "failed")),
        "none_found": [outcome["rule"] for outcome in outcomes
                       if outcome["status"] == "passed" and not outcome.get("evaluated")],
        "failed": [outcome["rule"] for outcome in outcomes if outcome["status"] == "failed"],
        "outcomes": outcomes,
        "sources": [source.as_data() for source in rule_set.sources],
    }
    return findings, record


def _plain(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
