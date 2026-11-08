"""The rules: what a manufacturing check compares its measurements against, each rule cited.

A check's measurements are facts (``cad.build123d``'s and ``cad.trimesh``'s reports). A process's **rules**
turn them into verdicts: one table per process (``RuleSet``), versioned, each rule a limit on one measured
field, the general practice a published design guide states -- the guide cited as the rule's evidence, never
as a shop's limit: text-to-cad's checks are no shop's, and a shop's own limits are read against the
measurements, which every result carries. A rule never changes a measurement and a verdict never replaces
one: the report carries both.

A rule reads ``report[family]``: a family's ``items`` (one record per feature, each with its ``location`` --
a ref in ``cad xbf inspect``'s grammar -- and ``xyz``), or the family itself where it has none (one figure
for the whole part). The limit is a number, or one number per value of a ``context`` key (``by``: the
material's class, a printing technology), times another (``scale_by``: a sheet's thickness), and the rule
applies only where the context matches ``when`` (elsewhere it is recorded ``not_applicable``, never dropped)
and to the items matching ``item_when`` (``not_applicable`` too where no item carries the fields it reads: a
mesh's walls, against a rule for supported walls). A family measured with nothing to judge -- no hole, no
wall under its threshold -- passes, ``none found``. A figure that was not measured, or a family that was
not, is no verdict: it is counted (``not_evaluated``), never passed. A table whose rules come in variants by
one context key (``RuleSet.selector``: printing's ``technology``) has no figure for a value none of a rule
id's variants names: that rule is ``not_evaluated`` too, and a check that evaluated nothing is said
(``rules_none_evaluated``, a warning) rather than read as a pass. Whatever its variants, the record holds
one outcome per rule id (``_one_per_rule``).

The standard library alone: the command resolves a check's options before it starts an environment.
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
    severity: str = "error"     # "error": the source's feasibility limit; "warning": its recommendation
    by: str | None = None       # the context key choosing the limit from a mapping
    scale_by: str | None = None  # the context key the limit is multiplied by
    when: Mapping[str, Any] = field(default_factory=dict)       # context key: value or tuple of values
    item_when: Mapping[str, Any] = field(default_factory=dict)  # item field: value or tuple of values
    fix: str = ""               # what to change, formatted with value, limit, unit, the context's and the item's plain values
    note: str = ""              # the source's own framing, paraphrased
    detail: str = ""            # appended to the message, formatted the same: "edge {edge}, {void_angle_deg:.0f} deg"

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
            scale = _number(context.get(self.scale_by))  # a bool is no scale: True is not x1
            if scale is None:
                return None
            value *= float(scale)
        return value

    def applies(self, context: Mapping[str, Any]) -> bool:
        return _matches(self.when, context)


@dataclass(frozen=True)
class RuleSet:
    """One process's versioned table of rules, and the sources they cite."""

    process: str
    title: str                  # "text-to-cad general rules"
    version: str                # the table's own version: "2026-11-08"
    rules: tuple[Rule, ...]
    sources: tuple[Source, ...]
    note: str = ""
    #: The context key the rules come in variants by (printing's ``technology``: one rule id, a limit and a
    #: severity per technology). A rule id with no variant for the context's value is ``not_evaluated`` (the
    #: table gives no limit here: unverified), never ``not_applicable`` as a rule for another context is.
    selector: str | None = None

    def __post_init__(self) -> None:
        known = {source.id for source in self.sources}
        for rule in self.rules:
            if rule.source not in known:
                raise ValueError(f"{self.process} rules: rule {rule.id} cites {rule.source!r}, which it does not list")

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
    # General practice, its guide the evidence: no verdict reads as a shop's limit.
    origin = f"general practice; source: {source.publisher}, {source.title}"
    # Four figures, or as many more as it takes for the value and the limit to read apart: a 0.999999998 mm wall
    # is under a 1 mm minimum, and its message must not say "1 mm is under the 1 mm minimum".
    digits = 4
    while digits < 17 and f"{value:.{digits}g}" == f"{limit:.{digits}g}":
        digits += 1
    # A warning is a recommendation, and says so: an agent reads "under the 1 deg minimum" as a limit the part
    # cannot be made under.
    bound = f"recommended {bound}" if rule.severity == "warning" else bound
    return (f"{rule.what} {value:.{digits}g} {rule.unit} is {relation} the {limit:.{digits}g} {rule.unit} {bound} "
            f"({origin})")


def _format(template: str, rule: Rule, value: float, limit: float, context: Mapping[str, Any],
            item: Mapping[str, Any]) -> str:
    """``template`` with the failure's value and limit, its unit, the context's plain values and the failing
    item's own (``{limit:g}``, ``{scs_radius_mm:.4g}``, ``{edge}``, ``{void_angle_deg:.0f}``; an item's ``xyz`` as
    text); the text as written where a name is missing."""
    fields = {key: found for key, found in context.items() if _plain(found)}
    fields.update({key: found for key, found in item.items() if _plain(found)})
    xyz = item.get("xyz")
    if isinstance(xyz, (list, tuple)):
        fields["xyz"] = ", ".join(f"{float(part):g}" for part in xyz)
    try:
        return template.format(**fields, value=value, limit=limit, unit=rule.unit)
    except (KeyError, IndexError, ValueError, TypeError):
        return template


def _hint(rule: Rule, value: float, limit: float, context: Mapping[str, Any], item: Mapping[str, Any]) -> str | None:
    return _format(rule.fix, rule, value, limit, context, item) if rule.fix else None


def evaluate(report: Mapping[str, Any], rule_set: RuleSet,
             context: Mapping[str, Any]) -> tuple[list[CheckFinding], dict[str, Any]]:
    """The verdicts of the process's rules (``rule_set``) on ``report`` in ``context``: findings (one per
    failing place, at most ``SHOWN_PER_RULE`` per rule, the rest counted in one more) and the record the
    report keeps of them (``measurements["rules"]``: the table, every rule's outcome, every failure's value,
    limit and place).

    The record holds every failure. The findings are what a reader acts on, so they are fewer: failures of
    one rule at one ref are one finding (``and N more at this ref``), and a warning on a figure that
    already fails an error -- the same family, field and direction at the same place, a recommendation
    beside the feasibility limit it exceeds -- is left to the record."""
    findings: list[CheckFinding] = []
    outcomes: list[dict[str, Any]] = []
    shown: list[tuple[Rule, float, list[dict[str, Any]], dict[int, Mapping[str, Any]]]] = []
    judged: dict[int, tuple[set[int], set[int]]] = {}
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
            outcome["reason"] = ("the rules give no limit here" if limit is None
                                 else f"{rule.family} was not measured")
            outcomes.append(outcome)
            continue
        if not readable:
            outcome.update(status="not_applicable", reason="this source's " + rule.family + " do not say "
                           + ", ".join(rule.item_when) + ": another rule judges them")
            outcomes.append(outcome)
            continue
        failures: list[dict[str, Any]] = []
        failing: dict[int, Mapping[str, Any]] = {}  # the item behind each failure, for its message; not recorded
        evaluated = unmeasured = 0
        judged[id(outcome)] = (read, unread) = (set(), set())  # the items, so variants of one rule count each once
        for item in items:
            value = _number(item.get(rule.field))
            if value is None:
                unmeasured += 1
                unread.add(id(item))
                continue
            evaluated += 1
            read.add(id(item))
            if _fails(rule, value, limit):
                failures.append({"value": value, "location": _where(item, rule), "xyz": item.get("xyz")})
                failing[id(failures[-1])] = item
        failures.sort(key=lambda found: found["value"], reverse=rule.op == "max")
        # Measured and nothing to judge -- no hole, no wall under the family's own threshold -- is a pass: none
        # found. A figure the items do not carry is no pass.
        status = "failed" if failures else "passed" if evaluated or not unmeasured else "not_evaluated"
        outcome.update(status=status, evaluated=evaluated, unmeasured=unmeasured, failures=failures)
        if not evaluated and not failures:
            outcome["reason"] = "none found: no feature it applies to" if not unmeasured else \
                f"{rule.field} was not measured"
        elif unmeasured:
            # Judged where measured: a pass over some items is not a pass over the rest.
            outcome["reason"] = f"{unmeasured} item(s) not measured"
        outcomes.append(outcome)
        if failures:
            shown.append((rule, limit, failures, failing))
    # Where an error names a figure of an item, a warning on the same figure of the same item is implied: keyed
    # by the item as well as its place, as items with no ref share one (a family's name, an xyz).
    failed_as_error = {(rule.family, rule.field, rule.op, failure["location"], id(failing.get(id(failure))))
                       for rule, _limit, failures, failing in shown if rule.severity == "error" for failure in failures}
    for rule, limit, failures, failing in shown:
        places: dict[str, list[dict[str, Any]]] = {}
        for failure in failures:
            key = (rule.family, rule.field, rule.op, failure["location"], id(failing.get(id(failure))))
            if rule.severity == "warning" and key in failed_as_error:
                continue
            places.setdefault(failure["location"], []).append(failure)
        for location, here in list(places.items())[:SHOWN_PER_RULE]:
            worst = here[0]
            item = failing.get(id(worst), {})
            detail = f" ({_format(rule.detail, rule, worst['value'], limit, context, item)})" if rule.detail else ""
            more = f" (and {len(here) - 1} more at this ref)" if len(here) > 1 else ""
            findings.append(CheckFinding(rule.severity, rule.id,
                                         _message(rule, rule_set, worst["value"], limit) + detail + more,
                                         location, _hint(rule, worst["value"], limit, context, item)))
        if len(places) > SHOWN_PER_RULE:
            # The rest, counted: where the record lists them, with the fix the first of them calls for.
            rest = list(places.values())[SHOWN_PER_RULE][0]
            findings.append(CheckFinding(rule.severity, rule.id,
                                         f"{len(places) - SHOWN_PER_RULE} more of the same "
                                         f"(measurements.rules lists every one)", "measurements.rules",
                                         _hint(rule, rest["value"], limit, context, failing.get(id(rest), {}))))
    outcomes = _one_per_rule(rule_set, context, outcomes, judged)
    record = {
        "title": rule_set.title, "version": rule_set.version, "note": rule_set.note,
        "context": {key: value for key, value in context.items() if _plain(value)},
        "evaluated": sum(1 for outcome in outcomes if outcome["status"] in ("passed", "failed")),
        "none_found": [outcome["rule"] for outcome in outcomes
                       if outcome["status"] == "passed" and not outcome.get("evaluated")],
        "failed": [outcome["rule"] for outcome in outcomes if outcome["status"] == "failed"],
        "outcomes": outcomes,
        "sources": [source.as_data() for source in rule_set.sources],
    }
    return findings, record


def _one_per_rule(rule_set: RuleSet, context: Mapping[str, Any], outcomes: list[dict[str, Any]],
                  judged: Mapping[int, tuple[set[int], set[int]]]) -> list[dict[str, Any]]:
    """``outcomes`` as one outcome per rule id, where the id's first stood. A rule id comes in variants -- by
    the context (``when``: a tool given or not, a technology), by its items (``item_when``: acute or square
    corners), a minimum and a maximum of one figure -- and the record answers for the id once:

    - the variants that judged (``passed``, ``failed``) are its outcome, merged where several did: ``failed``
      if any failed, each item counted once, every failure with its own limit, op and severity where the
      variants' differ (``variants`` lists them); a variant that applied but judged nothing (no limit here)
      is left out, its reason kept;
    - none judged: the one that applied and was not evaluated (no limit here, its family not measured);
    - every variant not applicable: one ``not_applicable``, the conditions joined -- but where every variant
      is for another value of the table's ``selector`` alone, ``not_evaluated``: the table has no figure for
      this value, which is no pass."""
    rules_by_id: dict[str, list[Rule]] = {}
    for rule in rule_set.rules:
        rules_by_id.setdefault(rule.id, []).append(rule)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["rule"], []).append(outcome)
    key = rule_set.selector
    one: list[dict[str, Any]] = []
    for ident, group in grouped.items():
        done = [outcome for outcome in group if outcome["status"] in ("passed", "failed")]
        unjudged = [outcome for outcome in group if outcome["status"] == "not_evaluated"]
        variants = rules_by_id[ident]
        if done:
            one.append(done[0] if len(done) == 1 and not unjudged else _merged(done, unjudged, judged))
        elif unjudged:
            one.append(unjudged[0])
        elif key is not None and all(set(rule.when) == {key} for rule in variants) and \
                not any(rule.applies(context) for rule in variants):
            first = variants[0]
            one.append({"rule": ident, "family": first.family, "field": first.field, "op": first.op,
                        "unit": first.unit, "severity": first.severity, "source": first.source,
                        "status": "not_evaluated",
                        "reason": f"the rules give no limit for {key} {context.get(key)}"})
        else:
            reasons = list(dict.fromkeys(str(outcome.get("reason") or "") for outcome in group))
            one.append({**group[0], "reason": "; or ".join(reason for reason in reasons if reason)})
    return one


def _merged(done: list[dict[str, Any]], unjudged: list[dict[str, Any]],
            judged: Mapping[int, tuple[set[int], set[int]]]) -> dict[str, Any]:
    """One rule id's outcome from its variants that judged (``done``) and those that applied but did not
    (``unjudged``): see ``_one_per_rule``."""
    first = next((outcome for outcome in done if outcome["status"] == "failed"), done[0])
    merged = dict(first)
    differ = len({(outcome["op"], outcome["limit"], outcome["severity"]) for outcome in done}) > 1
    failures = [{**failure, "op": outcome["op"], "limit": outcome["limit"], "severity": outcome["severity"]}
                if differ else failure for outcome in done for failure in outcome["failures"]]
    read = set().union(*(judged[id(outcome)][0] for outcome in done))
    unread = set().union(*(judged[id(outcome)][1] for outcome in done)) - read
    merged.update(status="failed" if failures else "passed", evaluated=len(read), unmeasured=len(unread),
                  failures=failures)
    if differ:
        merged["variants"] = [{"op": outcome["op"], "limit": outcome["limit"], "severity": outcome["severity"],
                               "status": outcome["status"], "failed": len(outcome["failures"])} for outcome in done]
    reasons = [*(["none found: no feature it applies to"] if not read and not unread else []),
               *([f"{len(unread)} item(s) not measured"] if read and unread else []),
               *dict.fromkeys(f"a variant not evaluated: {outcome['reason']}" for outcome in unjudged)]
    merged.pop("reason", None)
    if reasons:
        merged["reason"] = "; ".join(reasons)
    return merged


def _plain(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
