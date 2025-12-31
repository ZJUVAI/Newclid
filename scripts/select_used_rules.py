#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


RULE_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])(\d+sub_\d+)(?![A-Za-z0-9_])")
RULE_NAME_FULL_RE = re.compile(r"^(\d+sub_\d+)$")


def iter_json_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.json"))


def extract_rule_names_from_text(text: str) -> set[str]:
    return set(m.group(1) for m in RULE_NAME_RE.finditer(text))


def extract_rule_names_from_json(obj: Any) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            found.update(extract_rule_names_from_text(node))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str):
                    found.update(extract_rule_names_from_text(k))
                walk(v)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, tuple):
            for item in node:
                walk(item)
            return
        # numbers/bools/etc: ignore

    walk(obj)
    return found


def load_used_rule_names(c10s50k_dir: Path, *, verbose: bool = False) -> tuple[set[str], int, int]:
    used: set[str] = set()
    files = list(iter_json_files(c10s50k_dir))
    parsed_ok = 0
    parsed_fail = 0

    for p in files:
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            parsed_ok += 1
        except Exception as e:  # noqa: BLE001
            parsed_fail += 1
            if verbose:
                print(f"[warn] failed to parse {p}: {e}")
            continue

        used.update(extract_rule_names_from_json(data))

    return used, parsed_ok, parsed_fail


def parse_rules_norm(norm_file: Path) -> list[tuple[str, str]]:
    lines = [ln.rstrip("\n") for ln in norm_file.read_text(encoding="utf-8").splitlines()]

    rules: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        name = lines[i].strip()
        if not name:
            i += 1
            continue

        m = RULE_NAME_FULL_RE.match(name)
        if not m:
            # 如果遇到非规则名行，跳过（更鲁棒）
            i += 1
            continue

        # 找到下一行作为内容（允许中间有空行）
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            break
        content = lines[j]
        rules.append((name, content))
        i = j + 1

    return rules


def write_selected_rules(
    norm_rules: list[tuple[str, str]],
    used_rule_names: set[str],
    out_file: Path,
) -> tuple[int, int]:
    selected = [(n, c) for (n, c) in norm_rules if n in used_rule_names]

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        for name, content in selected:
            f.write(f"{name}\n")
            f.write(f"{content}\n")

    return len(selected), len(norm_rules)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "从 datasets/c10s50k 下所有 JSON 文件中提取形如 {id}sub_{k} 的规则名，"
            "并在 extracted_rules/c10s50k_rules_norm.txt 中按两行一组匹配，"
            "输出匹配到的规则到 datasets/tmp_used_rules.txt。"
        )
    )
    parser.add_argument(
        "--c10s50k-dir",
        type=Path,
        default=Path("datasets/c10s50k"),
        help="包含 JSON 结果文件的目录 (默认: datasets/c10s50k)",
    )
    parser.add_argument(
        "--norm-file",
        type=Path,
        default=Path("datasets/extracted_rules/c10s50k_rules_norm.txt"),
        help="规则库文件 (默认: datasets/extracted_rules/c10s50k_rules_norm.txt)",
    )
    parser.add_argument(
        "--out-file",
        type=Path,
        default=Path("datasets/tmp_used_rules.txt"),
        help="输出文件 (默认: datasets/tmp_used_rules.txt)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印解析失败的 JSON 文件等信息",
    )

    args = parser.parse_args()

    c10s50k_dir: Path = args.c10s50k_dir
    norm_file: Path = args.norm_file
    out_file: Path = args.out_file

    used, ok, fail = load_used_rule_names(c10s50k_dir, verbose=args.verbose)
    norm_rules = parse_rules_norm(norm_file)
    selected_cnt, total_norm = write_selected_rules(norm_rules, used, out_file)

    norm_rule_names = {n for (n, _c) in norm_rules}
    missing_in_norm = sorted(used - norm_rule_names)

    print(
        "\n".join(
            [
                f"JSON scanned ok/fail: {ok}/{fail}",
                f"Used rule names found in JSON: {len(used)}",
                f"Rules in norm file (parsed): {total_norm}",
                f"Selected rules written: {selected_cnt}",
                f"Used but missing in norm: {len(missing_in_norm)}",
                f"Output: {out_file}",
            ]
        )
    )

    if args.verbose and missing_in_norm:
        print("\n" + "\n".join(["Missing rule names (in JSON but not in norm):"] + missing_in_norm[:200]))
        if len(missing_in_norm) > 200:
            print(f"... and {len(missing_in_norm) - 200} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
