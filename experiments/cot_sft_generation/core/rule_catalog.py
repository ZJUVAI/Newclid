"""Rule catalog: maps DDAR rule IDs to human-readable theorem names."""

import re
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_RULES_FILE = Path(__file__).resolve().parents[3] / "src" / "newclid" / "default_configs" / "rules.txt"

_NUMERICAL_PREDICATES = frozenset({"sameclock", "ncoll", "nsameside", "sameside", "npara"})


@dataclass
class RuleEntry:
    rule_id: str
    raw_name: str
    human_name: str
    lhs_predicates: list = field(default_factory=list)
    rhs_predicates: list = field(default_factory=list)


_HUMAN_NAME_OVERRIDES = {
    "r03": "the inscribed angle theorem",
    "r04": "the converse of the inscribed angle theorem",
    "r07": "Thales' theorem",
    "r11": "the angle bisector theorem",
    "r12": "the angle bisector theorem (ratio form)",
    "r19": "the right-angle-in-semicircle theorem",
    "r27": "Thales' theorem (parallel ratio)",
    "r28": "overlapping parallels imply collinearity",
    "r34": "AA similarity",
    "r35": "AA similarity (reverse orientation)",
    "r41": "Thales' theorem (parallel transversal)",
    "r42": "Thales' theorem (ratio transversal)",
    "r43": "the orthocenter theorem",
    "r44": "Pappus' theorem",
    "r46": "the incenter angle theorem",
    "r49": "the circumcenter equidistance property",
    "r50": "the circumcenter equidistance property",
    "r51": "the midpoint ratio property",
    "r52": "the side-ratio property of similar triangles",
    "r53": "the side-ratio property of similar triangles (reverse)",
    "r54": "the midpoint definition",
    "r56": "the midpoint collinearity property",
    "r57": "the Pythagorean theorem",
    "r58": "equal chords subtend equal inscribed angles",
    "r59": "equal chords subtend equal inscribed angles (opposite arc)",
    "r60": "SSS similarity",
    "r61": "SSS similarity (reverse orientation)",
    "r62": "SAS similarity",
    "r63": "SAS similarity (reverse orientation)",
    "r101": "similarity with a shared side gives congruence",
    "r102": "similarity with a shared side gives congruence (reverse)",
}


def load_rule_catalog(rules_file=None):
    """Parse rules.txt into {rule_id: RuleEntry}."""
    path = Path(rules_file) if rules_file else _DEFAULT_RULES_FILE
    if not path.exists():
        return {}

    catalog = {}
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        header_match = re.match(r"^(r\d+)\s+(.+)$", lines[i].strip())
        if not header_match:
            i += 1
            continue
        rule_id = header_match.group(1)
        raw_name = header_match.group(2).strip()
        human_name = _HUMAN_NAME_OVERRIDES.get(rule_id, raw_name.lower())

        lhs_predicates = []
        rhs_predicates = []
        if i + 1 < len(lines):
            body_line = lines[i + 1].strip()
            if "=>" in body_line:
                lhs_part, rhs_part = body_line.split("=>", 1)
                lhs_predicates = _extract_predicates(lhs_part)
                rhs_predicates = _extract_predicates(rhs_part)
            i += 2
        else:
            i += 1

        catalog[rule_id] = RuleEntry(
            rule_id=rule_id,
            raw_name=raw_name,
            human_name=human_name,
            lhs_predicates=lhs_predicates,
            rhs_predicates=rhs_predicates,
        )
    return catalog


def _extract_predicates(clause_text):
    """Extract predicate names from a comma-separated clause list."""
    predicates = []
    for part in clause_text.split(","):
        tokens = part.strip().split()
        if tokens:
            predicates.append(tokens[0].lower())
    return predicates


_CATALOG_CACHE = None


def _get_catalog():
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        _CATALOG_CACHE = load_rule_catalog()
    return _CATALOG_CACHE


def humanize_rule(rule_id):
    """Return a human-readable phrase for a rule application.

    For AR returns "by algebraic combination".
    For unknown IDs returns "by a standard geometric identity".
    """
    if not rule_id:
        return "by a standard geometric identity"
    if rule_id.upper() == "AR":
        return "by algebraic combination"
    catalog = _get_catalog()
    entry = catalog.get(rule_id)
    if entry:
        return f"by {entry.human_name}"
    return "by a standard geometric identity"


def expected_numerical_predicates(rule_id):
    """Return the set of numerical-check predicates a rule requires in its LHS."""
    catalog = _get_catalog()
    entry = catalog.get(rule_id)
    if not entry:
        return set()
    return {pred for pred in entry.lhs_predicates if pred in _NUMERICAL_PREDICATES}
