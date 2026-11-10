"""The rules: what a manufacturing check compares its measurements against, each rule cited.

A check's measurements are facts (``cad.build123d``'s and ``cad.trimesh``'s reports). A process's **rules**
turn them into verdicts: one table per process (``RuleSet``), versioned, each rule a limit on one measured
field, the general practice a published design guide states -- the guide cited as the rule's evidence, never
as a shop's limit -- or, where no guide states a limit, text-to-cad's own floor, its source text-to-cad and
never a publisher (``_origin``): text-to-cad's checks are no shop's, and a shop's own limits are read against the
measurements, which every result carries. A rule never changes a measurement and a verdict never replaces
one: the report carries both.

A rule reads ``report[family]``: a family's ``items`` (one record per feature, each with its ``location`` --
a ref in ``cad xbf inspect``'s grammar -- and ``xyz``), or the family itself where it has none (one figure
for the whole part). The limit is a number, or one number per value of a ``context`` key (``by``: the
material's class, a printing technology), times another (``scale_by``: a sheet's thickness -- the item's own
figure of that name where it carries one, a part's own thickness among several, else the context's), and the
rule applies only where the context matches ``when`` (elsewhere it is recorded ``not_applicable``, never
dropped) and to the items matching ``item_when`` (``not_applicable`` too where no item carries the fields it
reads: a mesh's walls, against a rule for supported walls). A family measured with nothing to judge -- no
hole, no wall under its threshold -- passes, ``none found``.

**Does not apply, or was not measured.** An item with no figure for a rule (``None``) says which it is. A
figure that does not apply to the item -- a lone rib has no gap to a neighbour, an open step no width, a sharp
corner no tool that fits it -- is named in the item's ``not_applicable`` (a list of its fields): the rule asks
nothing of the item and nothing is missing. Any other missing figure was not measured, which is no verdict
and never a pass: the rule is ``partial`` (it judged the rest) or ``not_evaluated`` (it judged none), and
``rule_partly_judged`` names the items, which makes the check not checked (``manufacturing.finish``). A family
is the same: one a source does not measure by its nature is named in the report's ``not_measured`` (a mesh's
holes, a cut file's bends: ``{family: why}``), its rules ``not_evaluated`` with that reason and said once
(``families_not_measured``); one that failed is ``{"error": ...}`` (``measurement_failed``); one a report
simply lacks, where a rule that applies reads it, was not measured either, and its outcome says so
(``absent``), which ``finish`` says as ``measurement_failed`` too. A table whose rules come in
variants by one context key (``RuleSet.selector``: printing's ``technology``) has no figure for a value none
of a rule id's variants names: that rule is ``not_evaluated`` too, and a check that evaluated nothing is said
(``rules_none_evaluated``) rather than read as a pass. Whatever its variants, the record holds one outcome
per rule id (``_one_per_rule``).

A verdict is one finding per feature per rule: the feature is the item's most specific ref (a corner's edge
before the face it lies on), every ref the item names is listed (``refs``), and the figure, the limit, the
unit, the comparison and the source are the finding's own fields, so nothing is read out of its message.

The standard library alone: the command resolves a check's options before it starts an environment.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cad.results import CheckFinding

__all__ = ["OWN", "Rule", "RuleSet", "Source", "evaluate"]

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


#: The source of every limit that is text-to-cad's own, in every process's table: a feasibility floor or a
#: rule of thumb no published guide states. A rule that cites it says in its ``note`` what the figure rests on,
#: and its finding's ``source`` reads ``text-to-cad, ...``, never a publisher's name.
OWN = Source("text-to-cad", "text-to-cad", "its own figure: no published guide states one",
             "https://github.com/earthtojake/text-to-cad", "")


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
    scale_by: str | None = None  # what the limit is multiplied by: the item's figure of this name, else the context's
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

    def limit_for(self, context: Mapping[str, Any], item: Mapping[str, Any] | None = None) -> float | None:
        """The limit in this context -- for ``item``, where it carries the figure the limit scales by
        (``scale_by``: a part's own thickness, among parts of several) -- or None where the rule gives none."""
        limit = self.limit
        if isinstance(limit, Mapping):
            key = context.get(self.by) if self.by else None
            limit = limit.get(str(key)) if key is not None else None
            if limit is None:
                return None
        value = float(limit)
        if self.scale_by is not None:
            scale = _number(item.get(self.scale_by)) if item is not None else None  # a bool is no scale
            if scale is None:
                scale = _number(context.get(self.scale_by))
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


#: An angle within this of its limit is at it: a figure of degrees carries its pull's or its normal's rounding
#: (a 2 deg wall against a pull typed to nine digits reads 1.99999999), far above a length's float noise.
ANGLE_TOLERANCE_DEG = 1e-6


def _fails(rule: Rule, value: float, limit: float) -> bool:
    """Is ``value`` past ``limit``, beyond noise: a billionth of the limit, an angle's ``ANGLE_TOLERANCE_DEG``?"""
    slack = ANGLE_TOLERANCE_DEG if rule.unit == "deg" else 1e-9 * max(1.0, abs(limit))
    return value < limit - slack if rule.op == "min" else value > limit + slack


def _items(report: Mapping[str, Any], rule: Rule) -> tuple[list[tuple[int | None, Mapping[str, Any]]] | None, bool]:
    """The items the rule judges, each with its index in the family's ``items`` (None: the family itself, one
    figure for the whole part) -- None where the family was not measured -- and whether the family holds
    items the rule could read at all: False where every item lacks the fields its ``item_when`` reads (a
    mesh's walls, which do not say whether they are supported, against a rule for supported walls)."""
    family = report.get(rule.family)
    if not isinstance(family, Mapping) or "error" in family:
        return None, True
    items = family.get("items")
    if isinstance(items, list):
        listed = [(index, item) for index, item in enumerate(items) if isinstance(item, Mapping)]
        readable = not rule.item_when or not listed or any(
            all(item.get(key) is not None or _wants_none(wanted) for key, wanted in rule.item_when.items())
            for _, item in listed)
        return [(index, item) for index, item in listed if _matches(rule.item_when, item)], readable
    return [(None, family)], True


#: A ref in ``cad xbf inspect``'s grammar, as an item names a face, an edge or a vertex: ``plate/edge 17``.
_REF = re.compile(r"(?:^|/)(vertex|edge|face) \d+$")
_SPECIFIC = {"vertex": 0, "edge": 1, "face": 2}


def _refs(item: Mapping[str, Any]) -> list[str]:
    """Every ref the item names -- in ``location``, ``edge``, ``faces`` or any other field of its own, a ref
    or a list of them -- the most specific first (a vertex, an edge, a face), each kind in the item's order,
    its ``location`` before the rest of its kind."""
    found: dict[str, None] = {}
    location = item.get("location")
    for value in (location, *item.values()):
        for text in value if isinstance(value, (list, tuple)) else (value,):
            if isinstance(text, str) and _REF.search(text):
                found.setdefault(text)
    return sorted(found, key=lambda ref: _SPECIFIC[_REF.search(ref).group(1)])  # type: ignore[union-attr]


def _where(item: Mapping[str, Any], rule: Rule) -> str:
    """Where an item says it is: its ``location``, else its ``xyz``, else the family."""
    location = item.get("location")
    if location:
        return str(location)
    xyz = item.get("xyz")
    if xyz:
        return ", ".join(f"{float(value):g}" for value in xyz)
    return rule.family


def _feature(item: Mapping[str, Any], rule: Rule) -> str:
    """The feature a failing item is, for its finding's place: its own edge (or vertex) where it names one -- a
    corner is its edge, not one of the two faces that meet there, so two corners of one face are two features
    --, else where it says it is (``_where``)."""
    for key in ("vertex", "edge"):
        named = item.get(key)
        if isinstance(named, str) and _REF.search(named):
            return named
    return _where(item, rule)


def _message(rule: Rule, value: float, limit: float, severity: str | None = None) -> str:
    """The verdict in a line: the figure, its limit and which side of it. Where the limit comes from is the
    finding's ``source``, said once for a rule's every place."""
    relation = "under" if rule.op == "min" else "over"
    bound = "minimum" if rule.op == "min" else "maximum"
    # Four figures, or as many more as it takes for the value and the limit to read apart: a 0.999999998 mm wall
    # is under a 1 mm minimum, and its message must not say "1 mm is under the 1 mm minimum".
    digits = 4
    while digits < 17 and f"{value:.{digits}g}" == f"{limit:.{digits}g}":
        digits += 1
    # A warning is a recommendation, and says so: an agent reads "under the 1 deg minimum" as a limit the part
    # cannot be made under.
    bound = f"recommended {bound}" if (severity or rule.severity) == "warning" else bound
    return f"{rule.what} {value:.{digits}g} {rule.unit} is {relation} the {limit:.{digits}g} {rule.unit} {bound}"


def _origin(rule: Rule, rule_set: RuleSet) -> str:
    """Where the rule's limit comes from, for a finding's ``source``: the guide's publisher and its title (a
    limit of text-to-cad's own names text-to-cad, never a publisher): the evidence of general practice, or
    whose floor it is, never a shop's limit."""
    source = rule_set.source(rule.source)
    return f"{source.publisher}, {source.title}"


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
    failing feature per rule, at most ``SHOWN_PER_RULE`` per rule, the rest counted in one more that lists
    them) and the record the report keeps of them (``measurements["rules"]``: the table, every rule's
    outcome, every failure's value, limit, place and item).

    The record holds every failure. The findings are what a reader acts on, so they are fewer: failures of
    one rule at one feature -- the item's most specific ref, ``_feature`` -- are one finding (``and N more at
    this ref``, each in its ``items``), and a failure on a figure that already fails a rule of higher
    severity, or of the same severity with a limit further off -- the same family, field and direction at the
    same place: a recommendation beside the feasibility limit it exceeds, the looser of two recommendations
    -- is left to the record. ``record["failing"]`` counts the features each rule fails as the findings do,
    by severity: the one count a summary says.

    Every figure is compared as measured, never rounded first (a report keeps the figures its rules read to
    1e-9): the slack here, a billionth of the limit, absorbs only floating-point noise, so a value exactly at
    its limit (30 / 18 against 1 / 0.6) passes and one a ten-thousandth past it fails."""
    findings: list[CheckFinding] = []
    outcomes: list[dict[str, Any]] = []
    shown: list[tuple[Rule, list[dict[str, Any]], dict[int, Mapping[str, Any]]]] = []
    # per outcome: the items it read, and those it could not (with their places), so variants of one rule count
    # each item once
    judged: dict[int, tuple[dict[int, None], dict[int, str]]] = {}
    feature: dict[int, str] = {}  # each failure's feature, its finding's place; the record keeps the item's own
    for rule in rule_set.rules:
        if not rule.applies(context):
            # Recorded, never dropped: a rule that does not apply here is not a pass either.
            outcomes.append({"rule": rule.id, "family": rule.family, "field": rule.field, "op": rule.op,
                             "unit": rule.unit, "severity": rule.severity, "source": rule.source,
                             "status": "not_applicable", "reason": "applies only where " + ", ".join(
                                 f"{key} is {value}" for key, value in rule.when.items())})
            continue
        base = rule.limit_for(context)
        items, readable = _items(report, rule)
        # the limit of each item: its own where the rule scales by a figure the item carries, else the context's
        limits = [rule.limit_for(context, item) if rule.scale_by else base for _, item in items or ()]
        outcome: dict[str, Any] = {"rule": rule.id, "family": rule.family, "field": rule.field, "op": rule.op,
                                   "limit": base, "unit": rule.unit, "severity": rule.severity,
                                   "source": rule.source}
        if base is None and all(limit is None for limit in limits):
            outcome.update(status="not_evaluated", reason="the rules give no limit here")
            outcomes.append(outcome)
            continue
        if items is None:
            # Not measured: by the source's nature (the report says why), because it failed (its own error), or
            # because the report lacks it -- which no one has said yet (``absent``: ``finish`` does).
            family = report.get(rule.family)
            by_nature = (report.get("not_measured") or {}).get(rule.family)
            outcome.update(status="not_evaluated", reason=f"{rule.family} was not measured"
                           + (f": {by_nature}" if by_nature else ""))
            if not by_nature and not (isinstance(family, Mapping) and "error" in family):
                outcome["absent"] = True
            outcomes.append(outcome)
            continue
        if not readable:
            outcome.update(status="not_applicable", reason="this source's " + rule.family + " do not say "
                           + ", ".join(rule.item_when) + ": another rule judges them")
            outcomes.append(outcome)
            continue
        failures: list[dict[str, Any]] = []
        failing: dict[int, Mapping[str, Any]] = {}  # the item behind each failure, for its message; not recorded
        judged[id(outcome)] = (read, unread) = ({}, {})
        for (index, item), limit in zip(items, limits):
            value = _number(item.get(rule.field))
            if value is None and rule.field in (item.get("not_applicable") or ()):
                continue  # the figure does not apply to this item, and the item says so: nothing is missing
            if value is None or limit is None:
                unread[id(item)] = _feature(item, rule)
                continue
            read[id(item)] = None
            if _fails(rule, value, limit):
                refs = _refs(item)
                failures.append({"value": value, "location": _where(item, rule), "xyz": item.get("xyz"),
                                 **({"refs": refs} if refs else {}), **({"item": index} if index is not None else {}),
                                 **({"limit": limit} if limit != base else {})})
                failing[id(failures[-1])] = item
                feature[id(failures[-1])] = _feature(item, rule)
        failures.sort(key=lambda found: found["value"], reverse=rule.op == "max")
        # Faces the family's rays could not be intersected with (``unmeasured_faces``: the kernel failed there):
        # its figures there are not measured, each such face counted not measured -- never a pass.
        family = report.get(rule.family)
        lost = [str(ref) for ref in (family.get("unmeasured_faces") or ())] if isinstance(family, Mapping) else []
        outcome.update(status=_status(bool(failures), len(read), len(unread) + len(lost)), evaluated=len(read),
                       unmeasured=len(unread) + len(lost), failures=failures)
        _unmeasured(outcome, len(read), list(unread.values()), lost, rule.field)
        outcomes.append(outcome)
        if failures:
            shown.append((rule, failures, failing))
    # A failure is implied by another rule's on the same figure of the same item in the same direction whose
    # severity is higher, or the same with a limit further off: a recommendation beside the feasibility limit it
    # exceeds (a warning beside an error), the looser of two recommendations (``draft``'s 2 deg beside
    # ``draft_min``'s 0.5). Keyed by the item as well as its place, as items with no ref share one.
    rank = {"error": 0, "warning": 1}
    failing_rules: dict[tuple[Any, ...], list[tuple[Rule, float]]] = {}

    def limit_of(rule: Rule, failure: Mapping[str, Any]) -> float:
        return float(failure["limit"]) if "limit" in failure else float(rule.limit_for(context) or 0.0)

    for rule, failures, failing in shown:
        for failure in failures:
            key = (rule.family, rule.field, rule.op, failure["location"], id(failing.get(id(failure))))
            failing_rules.setdefault(key, []).append((rule, limit_of(rule, failure)))

    def implied(rule: Rule, limit: float, key: tuple[Any, ...]) -> bool:
        for other, other_limit in failing_rules.get(key, ()):
            if other.id == rule.id:
                continue
            if rank[other.severity] < rank[rule.severity] or (
                    rank[other.severity] == rank[rule.severity]
                    and (other_limit < limit if rule.op == "min" else other_limit > limit)):
                return True
        return False

    counts: dict[str, dict[str, int]] = {"error": {}, "warning": {}}
    for rule, failures, failing in shown:
        places: dict[str, list[dict[str, Any]]] = {}
        for failure in failures:
            key = (rule.family, rule.field, rule.op, failure["location"], id(failing.get(id(failure))))
            if implied(rule, limit_of(rule, failure), key):
                continue
            places.setdefault(feature[id(failure)], []).append(failure)
        if not places:
            continue
        counts[rule.severity][rule.id] = counts[rule.severity].get(rule.id, 0) + len(places)
        said = {"rule": rule.id, "unit": rule.unit, "op": rule.op, "source": _origin(rule, rule_set)}
        for location, here in list(places.items())[:SHOWN_PER_RULE]:
            worst = here[0]
            limit = limit_of(rule, worst)
            item = failing.get(id(worst), {})
            detail = f" ({_format(rule.detail, rule, worst['value'], limit, context, item)})" if rule.detail else ""
            more = f" (and {len(here) - 1} more at this ref)" if len(here) > 1 else ""
            findings.append(CheckFinding(
                rule.severity, rule.id, _message(rule, worst["value"], limit) + detail + more, location,
                _hint(rule, worst["value"], limit, context, item), value=worst["value"], limit=limit,
                refs=list(worst.get("refs") or ()),
                items=[{"value": found["value"], "xyz": found.get("xyz")} for found in here] if len(here) > 1 else [],
                **said))
        if len(places) > SHOWN_PER_RULE:
            # The rest, counted and listed: with the fix the first of them calls for.
            rest = list(places.items())[SHOWN_PER_RULE:]
            first = rest[0][1][0]
            findings.append(CheckFinding(
                rule.severity, rule.id, f"{len(rest)} more of the same (measurements.rules lists every one)",
                "measurements.rules",
                _hint(rule, first["value"], limit_of(rule, first), context, failing.get(id(first), {})),
                items=[{"location": location, "value": here[0]["value"], "refs": list(here[0].get("refs") or ())}
                       for location, here in rest], **said))
    outcomes = _one_per_rule(rule_set, context, outcomes, judged)
    for outcome in outcomes:
        # A rule that did not judge every item it has says so, whatever it made of the rest: a figure that was
        # not measured is no verdict (one that does not apply is the item's ``not_applicable``, and unsaid).
        lacking = outcome.pop("_unread", None) or []
        if lacking:
            shown_at = ", ".join(lacking[:3]) + (f" and {len(lacking) - 3} more" if len(lacking) > 3 else "")
            findings.append(CheckFinding(
                "warning", "rule_partly_judged",
                f"{outcome['rule']} judged {outcome['evaluated']} of {outcome['evaluated'] + len(lacking)} "
                f"{outcome['family']}: {len(lacking)} carry no {outcome['field']} ({shown_at}), which was not "
                f"measured, so the rule gives them no verdict", lacking[0],
                f"read measurements.{outcome['family']} for them and judge them by hand, or check again"))
    record = {
        "title": rule_set.title, "version": rule_set.version, "note": rule_set.note,
        "context": {key: value for key, value in context.items() if _plain(value)},
        "evaluated": sum(1 for outcome in outcomes if outcome["status"] in ("passed", "failed", "partial")),
        "none_found": [outcome["rule"] for outcome in outcomes
                       if outcome["status"] == "passed" and not outcome.get("evaluated")],
        "partial": [outcome["rule"] for outcome in outcomes if outcome["status"] == "partial"],
        "failed": [outcome["rule"] for outcome in outcomes if outcome["status"] == "failed"],
        "failing": counts,
        "outcomes": outcomes,
        "sources": [source.as_data() for source in rule_set.sources],
    }
    return findings, record


def _status(failed: bool, evaluated: int, unmeasured: int) -> str:
    """A rule's status from what it judged: ``failed`` where an item fails; ``not_evaluated`` where it judged
    none of the items it has; ``partial`` where it judged some and not the rest -- never ``passed``, which is
    every item judged, or none to judge (none found)."""
    if failed:
        return "failed"
    if unmeasured:
        return "partial" if evaluated else "not_evaluated"
    return "passed"


def _unmeasured(outcome: dict[str, Any], evaluated: int, lacking: list[str], lost: list[str], field_name: str) -> None:
    """What ``outcome`` says of the items it did not judge: its ``reason``, the faces the kernel failed on
    (``unmeasured_faces``) and, kept for the finding that names them, the places of the items that carry no
    figure (``_unread``, dropped before the record is written)."""
    outcome.pop("reason", None)
    outcome.pop("unmeasured_faces", None)
    said = []
    if lacking:
        said.append(f"{len(lacking)} item(s) not measured")
        outcome["_unread"] = lacking
    if lost:
        outcome["unmeasured_faces"] = lost
        named = ", ".join(lost[:8]) + (f" and {len(lost) - 8} more" if len(lost) > 8 else "")
        said.append(f"not measured at {len(lost)} face(s) the kernel failed to intersect rays with ({named})")
    if not evaluated and not outcome["failures"]:
        # Measured and nothing to judge -- no hole, no wall under the family's own threshold -- is a pass: none
        # found. A figure the items do not carry is no pass.
        outcome["reason"] = "none found: no feature it applies to" if not lacking and not lost else \
            "; ".join(said) if lost else f"{field_name} was not measured"
    elif said:
        # Judged where measured: a pass over some items is not a pass over the rest.
        outcome["reason"] = "; ".join(said)


def _one_per_rule(rule_set: RuleSet, context: Mapping[str, Any], outcomes: list[dict[str, Any]],
                  judged: Mapping[int, tuple[dict[int, None], dict[int, str]]]) -> list[dict[str, Any]]:
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
        done = [outcome for outcome in group if outcome["status"] in ("passed", "failed", "partial")]
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
            judged: Mapping[int, tuple[dict[int, None], dict[int, str]]]) -> dict[str, Any]:
    """One rule id's outcome from its variants that judged (``done``) and those that applied but did not
    (``unjudged``): see ``_one_per_rule``."""
    first = next((outcome for outcome in done if outcome["status"] == "failed"), done[0])
    merged = dict(first)
    differ = len({(outcome["op"], outcome["limit"], outcome["severity"]) for outcome in done}) > 1
    failures = [{"op": outcome["op"], "limit": outcome["limit"], "severity": outcome["severity"], **failure}
                if differ else failure for outcome in done for failure in outcome["failures"]]
    read: dict[int, None] = {}
    unread: dict[int, str] = {}
    for outcome in done:
        read.update(judged[id(outcome)][0])
        unread.update(judged[id(outcome)][1])
    lacking = [where for item, where in unread.items() if item not in read]
    lost = sorted({ref for outcome in done for ref in outcome.get("unmeasured_faces") or ()})
    merged.update(status=_status(bool(failures), len(read), len(lacking) + len(lost)),
                  evaluated=len(read), unmeasured=len(lacking) + len(lost), failures=failures)
    merged.pop("_unread", None)
    _unmeasured(merged, len(read), lacking, lost, merged["field"])
    if differ:
        merged["variants"] = [{"op": outcome["op"], "limit": outcome["limit"], "severity": outcome["severity"],
                               "status": outcome["status"], "failed": len(outcome["failures"])} for outcome in done]
    reasons = [*([merged["reason"]] if merged.get("reason") else []),
               *dict.fromkeys(f"a variant not evaluated: {outcome['reason']}" for outcome in unjudged)]
    merged.pop("reason", None)
    if reasons:
        merged["reason"] = "; ".join(reasons)
    return merged


def _plain(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
