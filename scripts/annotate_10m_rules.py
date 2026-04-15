#!/usr/bin/env python3
"""Auto-annotate extracted rules with Chinese geometric meaning."""

import re
import sys

PRED_CN = {
    "cong": "等距",
    "eqangle": "等角",
    "eqratio": "等比",
    "cyclic": "共圆",
    "para": "平行",
    "perp": "垂直",
    "coll": "共线",
    "midp": "中点",
    "contri": "全等三角形",
    "simtri": "相似三角形",
    "eqpoint": "点重合",
    "ncoll": "不共线",
    "sameclock": "同向",
}


def parse_rule(rule_text):
    """Parse a rule into premises and conclusion."""
    parts = rule_text.strip().split(" => ")
    if len(parts) != 2:
        return None, None
    prem_str, concl_str = parts
    premises = parse_predicates(prem_str)
    conclusion = parse_predicates(concl_str)
    return premises, conclusion


def parse_predicates(text):
    """Parse comma-separated predicates."""
    preds = []
    for part in text.split(", "):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if tokens:
            pred_name = tokens[0]
            args = tokens[1:]
            preds.append((pred_name, args))
    return preds


def describe_pred(pred_name, args):
    """Generate a short math description for a predicate."""
    A = [x.upper() for x in args]
    if pred_name == "cong" and len(A) == 4:
        return f"{A[0]}{A[1]}≅{A[2]}{A[3]}"
    elif pred_name == "eqangle" and len(A) == 8:
        return f"∠({A[0]}{A[1]},{A[2]}{A[3]})=∠({A[4]}{A[5]},{A[6]}{A[7]})"
    elif pred_name == "eqratio" and len(A) == 8:
        return f"{A[0]}{A[1]}/{A[2]}{A[3]}={A[4]}{A[5]}/{A[6]}{A[7]}"
    elif pred_name == "cyclic" and len(A) == 4:
        return f"{','.join(A)}共圆"
    elif pred_name == "para" and len(A) == 4:
        return f"{A[0]}{A[1]}∥{A[2]}{A[3]}"
    elif pred_name == "perp" and len(A) == 4:
        return f"{A[0]}{A[1]}⊥{A[2]}{A[3]}"
    elif pred_name == "coll" and len(A) == 3:
        return f"{','.join(A)}共线"
    elif pred_name == "midp" and len(A) == 3:
        return f"{A[0]}是{A[1]}{A[2]}中点"
    elif pred_name == "contri" and len(A) == 6:
        return f"△{A[0]}{A[1]}{A[2]}≅△{A[3]}{A[4]}{A[5]}"
    elif pred_name == "simtri" and len(A) == 6:
        return f"△{A[0]}{A[1]}{A[2]}∼△{A[3]}{A[4]}{A[5]}"
    elif pred_name == "eqpoint" and len(A) == 2:
        return f"{A[0]}≡{A[1]}"
    elif pred_name == "ncoll" and len(A) == 3:
        return f"{','.join(A)}不共线"
    elif pred_name == "sameclock":
        return "同向"
    else:
        return f"{pred_name}({','.join(A)})"


def generate_annotation(premises, conclusion):
    """Generate Chinese annotation for a rule."""
    # Premise types summary
    prem_types = []
    for pred_name, args in premises:
        cn = PRED_CN.get(pred_name, pred_name)
        if cn not in prem_types:
            prem_types.append(cn)

    # Conclusion type
    concl_types = []
    for pred_name, args in conclusion:
        cn = PRED_CN.get(pred_name, pred_name)
        if cn not in concl_types:
            concl_types.append(cn)

    arrow = "+".join(prem_types) + " → " + "+".join(concl_types)

    # Math description
    prem_descs = [describe_pred(n, a) for n, a in premises]
    concl_descs = [describe_pred(n, a) for n, a in conclusion]
    math = "若" + "且".join(prem_descs) + "，则" + "且".join(concl_descs)

    return f"{arrow}：{math}"


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else \
        "outputs/experiments/20260415_02_10m_rules_annotation/extracted_rules.txt"
    output_file = sys.argv[2] if len(sys.argv) > 2 else \
        "outputs/experiments/20260415_02_10m_rules_annotation/extracted_rules_annotated.txt"

    with open(input_file, "r") as f:
        lines = f.readlines()

    out_lines = []
    i = 0
    count = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # This should be the rule ID line
        rule_id = line
        if i + 1 < len(lines):
            rule_text = lines[i + 1].strip()
        else:
            break

        premises, conclusion = parse_rule(rule_text)
        if premises is not None and conclusion is not None:
            annotation = generate_annotation(premises, conclusion)
            out_lines.append(f"{rule_id}  # {annotation}")
            out_lines.append(rule_text)
            out_lines.append("")
            count += 1
        else:
            out_lines.append(f"{rule_id}  # [解析失败]")
            out_lines.append(rule_text)
            out_lines.append("")
            count += 1

        i += 2

    with open(output_file, "w") as f:
        f.write("\n".join(out_lines))

    print(f"Annotated {count} rules -> {output_file}")


if __name__ == "__main__":
    main()
