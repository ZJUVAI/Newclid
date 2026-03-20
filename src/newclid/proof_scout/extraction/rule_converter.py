#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuleConverter - Convert Proof Scout rules to DDAR-compatible format.

This module provides utilities to:
- Parse rules from Proof Scout output (premise1, premise2 => conclusion)
- Validate predicate names against DDAR's supported predicates
- Normalize point names to canonical form (a, b, c, ...)
- Output rules in DDAR-compatible format

No ML dependencies required.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# Valid predicates supported by DDAR engine
VALID_PREDICATES: Set[str] = {
    # Basic geometric predicates
    "coll",      # collinear points
    "cong",      # congruent segments
    "para",      # parallel lines
    "perp",      # perpendicular lines
    "cyclic",    # concyclic points
    "midp",      # midpoint
    "circle",    # circle through points
    # Angle and ratio predicates
    "eqangle",   # equal angles (8 args)
    "eqratio",   # equal ratios (8 args)
    "eqangle3",  # equal angles (6 args, simplified)
    "eqratio3",  # equal ratios (6 args, simplified)
    "rconst",    # ratio constant
    # Triangle predicates
    "simtri",    # similar triangles (direct)
    "simtrir",   # similar triangles (reverse)
    "contri",    # congruent triangles (direct)
    "contrir",   # congruent triangles (reverse)
    # Auxiliary predicates
    "sameclock", # same orientation
    "sameside",  # same side
    "ncoll",     # not collinear
    "npara",     # not parallel
    "nsameside", # not same side
    # Special predicates
    "PythagoreanPremises",
    "PythagoreanConclusions",
}

# Predicate aliases (map alternative names to canonical names)
PREDICATE_ALIASES: Dict[str, str] = {
    "collinear": "coll",
    "congruent": "cong",
    "parallel": "para",
    "perpendicular": "perp",
    "concyclic": "cyclic",
    "midpoint": "midp",
}


def _alpha_seq(n: int) -> str:
    """Generate alphabetic sequence: 0->a, 1->b, ..., 25->z, 26->aa, etc."""
    letters: List[str] = []
    while True:
        n, r = divmod(n, 26)
        letters.append(chr(ord('a') + r))
        if n == 0:
            break
        n -= 1
    return "".join(reversed(letters))


def _is_point_token(tok: str) -> bool:
    """Check if token is a valid point name (alphabetic identifier)."""
    if not tok:
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", tok))


def _is_numeric_token(tok: str) -> bool:
    """Check if token is a numeric value (e.g., 1/2, 0.5, 3)."""
    if not tok:
        return False
    # Match fractions like 1/2, decimals like 0.5, or integers
    return bool(re.match(r"^-?\d+(/\d+)?$", tok) or re.match(r"^-?\d+\.\d+$", tok))


def _parse_clause(clause: str) -> Tuple[str, List[str]]:
    """Parse a single clause into (predicate, [args]).

    Example: "cong a b c d" -> ("cong", ["a", "b", "c", "d"])
    """
    tokens = [t for t in (clause or "").strip().split() if t]
    if not tokens:
        return "", []
    return tokens[0].lower(), tokens[1:]


def _split_clauses(text: str) -> List[str]:
    """Split text by commas at top level (not inside parentheses)."""
    parts = [p.strip() for p in (text or "").split(",")]
    return [p for p in parts if p]


def _split_rule_text(rule_text: str) -> Tuple[List[Tuple[str, List[str]]], Tuple[str, List[str]]]:
    """Split rule text into premises and conclusion.

    Returns: ([(pred, args), ...], (pred, args))
    """
    if not isinstance(rule_text, str):
        return [], ("", [])

    if "=>" in rule_text:
        left, right = re.split(r"\s*=>\s*", rule_text.strip(), maxsplit=1)
    else:
        left, right = rule_text.strip(), ""

    left_parsed = [_parse_clause(c) for c in _split_clauses(left)] if left else []
    right_parsed = _parse_clause(right) if right else ("", [])

    return left_parsed, right_parsed


class RuleConverter:
    """Convert Proof Scout rules to DDAR-compatible format."""

    def __init__(
        self,
        valid_predicates: Optional[Set[str]] = None,
        predicate_aliases: Optional[Dict[str, str]] = None,
        strict_validation: bool = True,
    ):
        """Initialize RuleConverter.

        Args:
            valid_predicates: Set of valid predicate names. Defaults to VALID_PREDICATES.
            predicate_aliases: Dict mapping aliases to canonical names.
            strict_validation: If True, reject rules with invalid predicates.
        """
        self.valid_predicates = valid_predicates or VALID_PREDICATES
        self.predicate_aliases = predicate_aliases or PREDICATE_ALIASES
        self.strict_validation = strict_validation

    def normalize_predicate(self, pred: str) -> str:
        """Normalize predicate name (lowercase, resolve aliases)."""
        pred_lower = pred.lower()
        return self.predicate_aliases.get(pred_lower, pred_lower)

    def validate_predicate(self, pred: str) -> bool:
        """Check if predicate is valid."""
        normalized = self.normalize_predicate(pred)
        return normalized in self.valid_predicates

    def validate_rule(self, rule_text: str) -> Tuple[bool, List[str]]:
        """Validate all predicates in a rule.

        Returns: (is_valid, list_of_invalid_predicates)
        """
        left_parsed, right_parsed = _split_rule_text(rule_text)

        invalid_preds: List[str] = []

        for pred, _ in left_parsed:
            if pred and not self.validate_predicate(pred):
                invalid_preds.append(pred)

        if right_parsed[0] and not self.validate_predicate(right_parsed[0]):
            invalid_preds.append(right_parsed[0])

        return len(invalid_preds) == 0, invalid_preds

    def normalize_points(self, rule_text: str) -> Tuple[str, Dict[str, str]]:
        """Normalize point names to canonical form (a, b, c, ...).

        Returns: (normalized_rule_text, rename_map)
        """
        left_parsed, right_parsed = _split_rule_text(rule_text)

        # Collect points in order of appearance
        seq: List[str] = []

        def collect(args: List[str]) -> None:
            for a in args:
                if _is_point_token(a) and not _is_numeric_token(a) and a not in seq:
                    seq.append(a)

        for _, args in left_parsed:
            collect(args)
        collect(right_parsed[1])

        # Create rename map
        rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

        def fmt(pred: str, args: List[str]) -> str:
            normalized_pred = self.normalize_predicate(pred)
            mapped = []
            for a in args:
                if _is_point_token(a) and not _is_numeric_token(a) and a in rename:
                    mapped.append(rename[a])
                else:
                    mapped.append(a)
            return (normalized_pred + (" " + " ".join(mapped) if mapped else "")).strip()

        left_norm = ", ".join([fmt(n, a) for n, a in left_parsed if n])
        right_norm = fmt(*right_parsed) if right_parsed[0] else ""

        if left_norm and right_norm:
            normalized = f"{left_norm} => {right_norm}"
        elif right_norm:
            normalized = f"=> {right_norm}"
        else:
            normalized = left_norm

        return normalized, rename

    def parse_scout_rules(self, path: Path) -> List[Tuple[str, str]]:
        """Parse rules from Proof Scout output file.

        Expected format (alternating lines):
            rule_id
            premise1, premise2 => conclusion
            rule_id
            premise1 => conclusion
            ...

        Returns: List of (rule_id, rule_text) tuples
        """
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {path}")

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        rules: List[Tuple[str, str]] = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Check if this is a rule ID line (starts with 'r' followed by digits)
            if re.match(r"^r\d+", line):
                rule_id = line
                if i + 1 < len(lines):
                    rule_text = lines[i + 1].strip()
                    if "=>" in rule_text:
                        rules.append((rule_id, rule_text))
                    i += 2
                else:
                    i += 1
            else:
                # Might be a rule without explicit ID
                if "=>" in line:
                    rules.append((f"r{len(rules):04d}", line))
                i += 1

        return rules

    def to_ddar_format(self, rule_id: str, rule_text: str) -> Optional[str]:
        """Convert a single rule to DDAR format.

        Returns: DDAR-formatted rule string, or None if invalid
        """
        # Validate predicates
        is_valid, invalid_preds = self.validate_rule(rule_text)
        if not is_valid and self.strict_validation:
            return None

        # Normalize points
        normalized, _ = self.normalize_points(rule_text)

        # Format as DDAR rule (description line + rule line)
        return f"{rule_id}\n{normalized}"

    def convert_file(
        self,
        input_path: Path,
        output_path: Path,
        skip_invalid: bool = True,
    ) -> Dict[str, Any]:
        """Convert a Proof Scout rules file to DDAR format.

        Args:
            input_path: Path to input rules file
            output_path: Path to output DDAR rules file
            skip_invalid: If True, skip rules with invalid predicates

        Returns: Statistics dict with conversion results
        """
        rules = self.parse_scout_rules(input_path)

        converted: List[str] = []
        skipped: List[Tuple[str, str, List[str]]] = []  # (rule_id, rule_text, invalid_preds)

        for rule_id, rule_text in rules:
            is_valid, invalid_preds = self.validate_rule(rule_text)

            if not is_valid:
                if skip_invalid:
                    skipped.append((rule_id, rule_text, invalid_preds))
                    continue

            ddar_rule = self.to_ddar_format(rule_id, rule_text)
            if ddar_rule:
                converted.append(ddar_rule)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(converted) + ("\n" if converted else ""))

        # Write skipped rules if any
        if skipped:
            skipped_path = output_path.with_name(output_path.stem + "_skipped.txt")
            with open(skipped_path, "w", encoding="utf-8") as f:
                for rule_id, rule_text, invalid_preds in skipped:
                    f.write(f"{rule_id} invalid_predicates={invalid_preds}\n")
                    f.write(f"{rule_text}\n")

        return {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "total_rules": len(rules),
            "converted": len(converted),
            "skipped": len(skipped),
            "skipped_rules": [(rid, preds) for rid, _, preds in skipped],
        }

    def convert_rules_list(
        self,
        rules: List[Tuple[str, str]],
        skip_invalid: bool = True,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, List[str]]]]:
        """Convert a list of rules to DDAR format.

        Args:
            rules: List of (rule_id, rule_text) tuples
            skip_invalid: If True, skip rules with invalid predicates

        Returns: (converted_rules, skipped_rules)
            converted_rules: List of (rule_id, normalized_rule_text)
            skipped_rules: List of (rule_id, rule_text, invalid_preds)
        """
        converted: List[Tuple[str, str]] = []
        skipped: List[Tuple[str, str, List[str]]] = []

        for rule_id, rule_text in rules:
            is_valid, invalid_preds = self.validate_rule(rule_text)

            if not is_valid:
                if skip_invalid:
                    skipped.append((rule_id, rule_text, invalid_preds))
                    continue

            normalized, _ = self.normalize_points(rule_text)
            converted.append((rule_id, normalized))

        return converted, skipped


__all__ = ["RuleConverter", "VALID_PREDICATES", "PREDICATE_ALIASES"]
