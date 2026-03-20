#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FilterAndPruneEngine

职责：封装 scripts/filter_and_prune.py 中的完整流程为可复用类，便于脚本薄封装调用：
  - 读取“新格式”数据（仅支持 llm_input_renamed / llm_output_renamed）
  - 过滤 aux_points 非空的题目
  - 使用 SingleProofGraph + GraphPruner 进行图修剪
  - 基于修剪结果生成不含辅助点的命题与规则文本，去重并落盘 *_pruned_rules.txt
  - 可选并行渲染筛选前/修剪后对比图

不引入新依赖；复用 data_discovery 中现有类。
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 仅在工作进程中延迟导入可视化相关库，避免非必须环境依赖

# ------------------------- 正则与通用解析工具 -------------------------
_TAG_RE = re.compile(r"</?\w+>")
# 放宽参数匹配字符集，允许包含 '.', '/', '-' 等（例如 rconst a b a c 1/2 [000]）
_FACT_SEG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\s+(?:[A-Za-z0-9_./-]+\s+)*\[\d+\]")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text or "")


def _extract_tag_content(text: str, tag: str) -> str:
    if not text:
        return ""
    pattern = re.compile(rf"<{tag}>" r"(.*?)" rf"</{tag}>", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1)
    return ""


def _sanitize_clause_section(raw: str) -> str:
    if not raw:
        return ""
    content = _strip_tags(raw).replace("\n", " ")
    clauses = [seg.strip() for seg in content.split(";") if seg.strip()]
    return "; ".join(clauses)


def _norm_text_basic(s: str) -> str:
    """基本规范化：去标签、换行转空格、多空白压缩、去首尾空白。
    保持项的相对顺序，不做标点/分号重排，避免引入语义漂移。
    """
    if not s:
        return ""
    s = _strip_tags(s)
    s = s.replace("\n", " ")
    # 压缩多空白为单空格
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _extract_problem_prefix_before_q(llm_input: str) -> str:
    """从 llm_input_renamed 提取 <problem> 标签内部问号前的内容；若无标签，则使用原始字符串。
    若找不到问号，则取全部。
    返回规范化后的文本（_norm_text_basic）。
    """
    if not isinstance(llm_input, str):
        return ""
    body = _extract_tag_content(llm_input, "problem") or llm_input
    # 仅取问号之前的部分
    qpos = body.find("?")
    if qpos >= 0:
        body = body[:qpos]
    return _norm_text_basic(body)


def _extract_aux_body_text(llm_output: str) -> str:
    """从 llm_output_renamed 中提取 <aux> 标签内部内容并规范化。缺失视为空。"""
    if not isinstance(llm_output, str):
        return ""
    aux_body = _extract_tag_content(llm_output, "aux")
    return _norm_text_basic(aux_body)


def _record_dedup_key(rec: Dict[str, Any]) -> Optional[str]:
    """生成用于去重的键：基于题干(问号前) + aux 内容。
    若关键字段缺失导致无法稳定抽取，则返回 None（放弃去重，保留该条）。
    """
    try:
        q = _extract_problem_prefix_before_q(rec.get("llm_input_renamed", ""))
        a = _extract_aux_body_text(rec.get("llm_output_renamed", ""))
        if not q and not a:
            return None
        combo = f"Q::{q}||A::{a}"
        return hashlib.sha1(combo.encode("utf-8")).hexdigest()
    except Exception:
        return None


def _dedup_by_question_and_aux(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """对 records 进行基于(题干+aux)的哈希去重。
    - 缺关键字段或解析异常的样本不参与去重（视为独特，直接保留）。
    - 返回 (去重后的列表, 统计信息)。
    """
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    removed = 0
    removed_ids: List[str] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = _record_dedup_key(rec)
        if not key:
            out.append(rec)
            continue
        if key in seen:
            removed += 1
            pid = rec.get("problem_id")
            if pid is not None:
                removed_ids.append(str(pid))
            continue
        seen.add(key)
        out.append(rec)
    return out, {"removed": removed, "kept": len(out), "removed_ids": removed_ids}


def _extract_fact_segments(text: str) -> List[str]:
    if not text:
        return []
    content = _strip_tags(text).replace("\n", " ")
    return [seg.strip() for seg in _FACT_SEG_RE.findall(content) if seg.strip()]


def _extract_aux_points(aux_section: str) -> List[str]:
    content = _strip_tags(aux_section).replace("\n", " ")
    aux_points: List[str] = []
    for part in content.split(";"):
        tokens = [tok for tok in part.strip().split() if tok]
        if len(tokens) >= 2 and tokens[0].lower().startswith("x"):
            aux_points.append(tokens[1])
    return aux_points


def _has_llm_format(record: Dict[str, Any]) -> bool:
    return isinstance(record, dict) and (
        "llm_input_renamed" in record or "llm_output_renamed" in record
    )


def _sanitize_basename(path: Path) -> str:
    stem = path.stem or "input"
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", stem)


def _convert_llm_record(record: Dict[str, Any], base: str, index: int) -> Dict[str, Any]:
    llm_input = record.get("llm_input_renamed", "")
    llm_output = record.get("llm_output_renamed", "")

    problem_id = record.get("problem_id")
    if not problem_id:
        problem_id = f"{base}:{index:06d}"

    problem_section = _extract_tag_content(llm_input, "problem") or llm_input
    analysis_segments = _extract_fact_segments(problem_section)
    aux_section = _extract_tag_content(llm_output, "aux")
    analysis_segments.extend(_extract_fact_segments(aux_section))
    analysis = "; ".join(analysis_segments)
    numerical = _sanitize_clause_section(_extract_tag_content(llm_output, "numerical_check"))
    proof_text = _sanitize_clause_section(_extract_tag_content(llm_output, "proof"))
    aux_points = _extract_aux_points(aux_section)
    existing_aux = record.get("aux_points")
    if isinstance(existing_aux, list) and existing_aux:
        aux_points = existing_aux

    converted = dict(record)
    converted["problem_id"] = problem_id
    converted["proof"] = {
        "analysis": analysis,
        "numerical_check": numerical,
        "proof": proof_text,
    }
    converted["aux_points"] = aux_points
    return converted


def _read_input_payload(path: Path) -> Any:
    data = path.read_text(encoding="utf-8")
    if not data.strip():
        return {"results": []}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        results = []
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            results.append(json.loads(line))
        return {"results": results}


def _normalize_input_object(path: Path) -> Dict[str, Any]:
    payload = _read_input_payload(path)
    base = _sanitize_basename(path)

    def convert_list(raw_list: List[Any]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw_list):
            if isinstance(item, dict) and _has_llm_format(item):
                converted.append(_convert_llm_record(item, base, idx))
            else:
                raise ValueError(
                    "filter_and_prune 仅支持包含 llm_input_renamed / llm_output_renamed 的新格式数据"
                )
        return converted

    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            normalized_results = convert_list(results)
        elif results is None:
            normalized_results = []
        else:
            raise ValueError("results 字段必须为列表")
        normalized = {k: v for k, v in payload.items() if k != "results"}
        normalized["results"] = normalized_results
        return normalized
    if isinstance(payload, list):
        normalized_results = convert_list(payload)
        return {"results": normalized_results}
    raise ValueError("输入文件必须为 JSON 对象或数组（新格式）")


def _combine_pngs_h(left_png: Path, right_png: Path, out_png: Path, *, title: Optional[str] = None, subtitle: Optional[str] = None) -> str:
    """将两张 PNG 水平合并为一张，并在子图上方标注标题与副标题。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
    except Exception as e:
        raise RuntimeError(
            "缺少 matplotlib，无法进行合图保存。请安装 matplotlib 后重试。"
        ) from e

    img_l = mpimg.imread(str(left_png))
    img_r = mpimg.imread(str(right_png))

    fig, axes = plt.subplots(1, 2, figsize=(30, 20))
    axes[0].imshow(img_l)
    axes[0].axis("off")
    axes[0].set_title("Original", fontsize=10)

    axes[1].imshow(img_r)
    axes[1].axis("off")
    axes[1].set_title("Pruned", fontsize=10)

    if title:
        fig.suptitle(title, fontsize=12)
    if subtitle:
        sub = subtitle if len(subtitle) <= 220 else (subtitle[:217] + "...")
        fig.text(0.5, 0.015, "proposition w/o aux: " + sub, ha='center', va='bottom', fontsize=11, bbox=dict(boxstyle='round', fc='white', ec='#999999', alpha=0.85))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(str(out_png), dpi=200)
    plt.close(fig)
    return str(out_png)


def _parse_args_from_label(raw_label: str) -> List[str]:
    try:
        if "(" in raw_label and ")" in raw_label:
            inside = raw_label.split("(", 1)[1].rsplit(")", 1)[0]
            parts = [p.strip() for p in inside.split(",") if p.strip()]
            return parts
    except Exception:
        pass
    return []


def _is_point_token(tok: str) -> bool:
    if not tok:
        return False
    return re.match(r"^[A-Za-z][A-Za-z0-9_]*$", tok) is not None


def _alpha_seq(n: int) -> str:
    letters: List[str] = []
    while True:
        n, r = divmod(n, 26)
        letters.append(chr(ord('a') + r))
        if n == 0:
            break
        n -= 1
    return "".join(reversed(letters))


def _parse_name_args(raw_label: str) -> Tuple[str, List[str]]:
    name = raw_label
    args = _parse_args_from_label(raw_label)
    if "(" in raw_label:
        name = raw_label.split("(", 1)[0].strip()
    return name, args


def _to_rule_text(premises: List[str], conclusion: str) -> Tuple[str, Dict[str, str]]:
    seq: List[str] = []

    def _collect(args: List[str]):
        for a in args:
            if _is_point_token(a) and a not in seq:
                seq.append(a)

    parsed_prems: List[Tuple[str, List[str]]] = []
    for pl in premises:
        pn, pa = _parse_name_args(str(pl))
        parsed_prems.append((pn, pa))
        _collect(pa)
    cn, ca = _parse_name_args(str(conclusion))
    _collect(ca)

    rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

    def _fmt(name: str, args: List[str]) -> str:
        out: List[str] = []
        for a in args:
            if _is_point_token(a) and a in rename:
                out.append(rename[a])
            else:
                out.append(a)
        return name + (" " + " ".join(out) if out else "")

    prem_txts = [_fmt(n, a) for (n, a) in parsed_prems]
    concl_txt = _fmt(cn, ca)
    rule_text = (", ".join(prem_txts) + " => " + concl_txt) if prem_txts else ("=> " + concl_txt)
    return rule_text, rename


def _split_clauses(text: str) -> List[str]:
    parts = [p.strip() for p in (text or "").split(",")]
    return [p for p in parts if p]


def _parse_clause(clause: str) -> Tuple[str, List[str]]:
    tokens = [t for t in (clause or "").strip().split() if t]
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


def _split_rule_text(rule_text: str) -> Tuple[List[Tuple[str, List[str]]], Tuple[str, List[str]]]:
    if not isinstance(rule_text, str):
        return [], ("", [])
    if "=>" in rule_text:
        left, right = re.split(r"\s*=>\s*", rule_text.strip(), maxsplit=1)
    else:
        left, right = rule_text.strip(), ""
    left_parsed = [_parse_clause(c) for c in _split_clauses(left)] if left else []
    right_parsed = _parse_clause(right) if right else ("", [])
    return left_parsed, right_parsed


def _collect_point_set(clauses: Iterable[Tuple[str, List[str]]]) -> set[str]:
    points: set[str] = set()
    for _, args in clauses:
        for arg in args:
            if _is_point_token(arg):
                points.add(arg)
    return points


def _collect_point_list(args: Iterable[str]) -> List[str]:
    return [a for a in args if _is_point_token(a)]


def _canonicalize_rule_text(rule_text: str) -> str:
    left_parsed, right_parsed = _split_rule_text(rule_text)

    seq: List[str] = []

    def collect(args: Iterable[str]) -> None:
        for a in args:
            if _is_point_token(a) and a not in seq:
                seq.append(a)

    for _, args in left_parsed:
        collect(args)
    collect(right_parsed[1])

    rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

    def fmt(name: str, args: List[str]) -> str:
        mapped = [rename.get(a, a) if _is_point_token(a) else a for a in args]
        return (name + (" " + " ".join(mapped) if mapped else "")).strip()

    left_norm = ", ".join([fmt(n, a) for n, a in left_parsed if n])
    right_norm = fmt(*right_parsed) if right_parsed[0] else ""
    if left_norm and right_norm:
        return f"{left_norm} => {right_norm}"
    if right_norm:
        return f"=> {right_norm}"
    return left_norm


def _fmt_rule_id(idx: int) -> str:
    return f"r{idx:04d}"


def _build_proposition_no_aux(rendered: Dict[str, Any], aux_points: List[str]) -> Optional[Dict[str, Any]]:
    nodes = (rendered or {}).get("nodes") or []
    edges = (rendered or {}).get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes:
        return None

    indeg = {n.get("idx"): 0 for n in nodes}
    outdeg = {n.get("idx"): 0 for n in nodes}
    for u, v in edges:
        outdeg[u] = outdeg.get(u, 0) + 1
        indeg[v] = indeg.get(v, 0) + 1

    fact_nodes = {n.get("idx"): n for n in nodes if n.get("type") == "fact"}
    premise_ids = [idx for idx, n in fact_nodes.items() if indeg.get(idx, 0) == 0]
    concl_ids = [idx for idx, n in fact_nodes.items() if outdeg.get(idx, 0) == 0]
    if len(concl_ids) != 1:
        return None

    aux_set = set(aux_points or [])
    kept_premises: List[str] = []
    for pid in premise_ids:
        raw_label = str(fact_nodes[pid].get("label", ""))
        args = _parse_args_from_label(raw_label)
        if not any(a in aux_set for a in args):
            kept_premises.append(raw_label)

    concl_label = str(fact_nodes[concl_ids[0]].get("label", ""))
    text = (", ".join(kept_premises) + " -> " + concl_label) if kept_premises else ("-> " + concl_label)
    return {"premises": kept_premises, "conclusion": concl_label, "text": text}


def _worker_prune(rec: Dict[str, Any]) -> Tuple[str, Any]:
    try:
        pid_val = rec.get("problem_id")
        if pid_val is None:
            return ("<none>", None)
        pid = str(pid_val)
        # 延迟导入，降低主进程依赖
        from newclid.data_discovery.graph_pruner import GraphPruner
        from newclid.data_discovery.single_proof_graph import SingleProofGraph
        pruner = GraphPruner()
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        rendered_one = pruner.prune_proof_graph(spg).get(pid)
        return (pid, rendered_one)
    except Exception:
        return (str(rec.get("problem_id")), None)


def _worker_render_combined(
    rec: Dict[str, Any],
    rendered: Dict[str, Any],
    out_png: str,
    label_mode: str,
    single_figsize: Tuple[int, int],
    ranksep: float,
    nodesep: float,
    font_size: int,
) -> Tuple[str, str]:
    try:
        from pathlib import Path as _Path
        import tempfile as _tempfile
        from newclid.data_discovery.proof_graph_visualizer import ProofGraphVisualizer
        from newclid.data_discovery.single_proof_graph import SingleProofGraph

        pid = str(rec.get("problem_id"))
        viz_left = ProofGraphVisualizer()
        viz_left.LAYOUT_RANKSEP = ranksep
        viz_left.LAYOUT_NODESEP = nodesep
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        with _tempfile.TemporaryDirectory() as td:
            td_path = _Path(td)
            left_png = td_path / f"left_{pid}.png"
            right_png = td_path / f"right_{pid}.png"
            viz_left.render_problem(spg, pid, str(left_png), label_mode=label_mode, highlight=True, figsize=single_figsize)
            # 修剪图（附 aux_points）
            rendered2 = dict(rendered)
            aux_points = rec.get("aux_points") or []
            if isinstance(aux_points, list):
                rendered2["aux_points"] = aux_points
            viz_right = ProofGraphVisualizer()
            viz_right.render_rendered(
                rendered2,
                str(right_png),
                label_mode=label_mode,
                highlight=True,
                figsize=single_figsize,
                font_size=font_size,
                show_direction_legend=True,
                layout_ranksep=ranksep,
                layout_nodesep=nodesep,
            )
            # 合图副标题优先使用规则文本
            prop = _build_proposition_no_aux(rendered2, list(rec.get("aux_points") or []))
            subtitle = None
            if isinstance(prop, dict):
                try:
                    rule_text, _ = _to_rule_text(prop.get("premises", []) or [], prop.get("conclusion", ""))
                    subtitle = rule_text
                except Exception:
                    subtitle = prop.get("text")
            _combine_pngs_h(left_png, right_png, _Path(out_png), title=f"Problem {pid}", subtitle=subtitle)
        return (pid, "ok")
    except Exception:
        return (str(rec.get("problem_id")), "failed")


class FilterAndPruneEngine:
    """一键筛选 + 修剪 + 规则提取（可并行绘图）的引擎类。"""

    def __init__(
        self,
        *,
        label_mode: str = "legend",
        figsize_single: Tuple[int, int] = (15, 20),
        figsize_combined: Tuple[int, int] = (30, 20),
        font_size: int = 9,
        ranksep: float = 2.8,
        nodesep: float = 1.2,
        overwrite: bool = True,
        progress_every: int = 10,
        max_workers: int = 50,
        # 若为 True，则在规则写出阶段打印并另存被跳过（无效）的规则，便于调试
        print_skipped_rules: bool = True,
        # 若为 True，则在绘图阶段打印并保存被跳过样本及原因
        print_render_skipped: bool = True,
        # 若为 True，则打印/保存去重阶段被移除的 pid 列表
        print_dedup_removed: bool = True,
        # 若为 True，则为所有参与处理的 pid 导出对应题目输入文本（JSONL），便于按 pid 检索题目
        save_pid_inputs: bool = True,
        # 新增：是否生成按规则编号的图片 rXXXX.png 及 rid_map.txt
        render_by_rule: bool = True,
        # 新增：是否保留/生成按 pid 命名的图片 proof_{pid}.png（默认关闭）
        keep_pid_images: bool = False,
        # 新增：谓词对称性配置文件路径（JSON），用于规则级去重的规范化
        symmetry_config_path: Optional[str] = None,
    ) -> None:
        self.label_mode = label_mode
        self.figsize_single = figsize_single
        self.figsize_combined = figsize_combined
        self.font_size = font_size
        self.ranksep = ranksep
        self.nodesep = nodesep
        self.overwrite = overwrite
        self.progress_every = progress_every
        self.max_workers = max_workers
        self.print_skipped_rules = print_skipped_rules
        self.print_render_skipped = print_render_skipped
        self.print_dedup_removed = print_dedup_removed
        self.save_pid_inputs = save_pid_inputs
        self.render_by_rule = render_by_rule
        self.keep_pid_images = keep_pid_images
        self.symmetry_config_path = symmetry_config_path
        # 预加载对称性配置（若提供）
        self._symmetry_cfg: Dict[str, Any] = {}
        if self.symmetry_config_path:
            try:
                p = Path(self.symmetry_config_path)
                if p.exists():
                    with open(p, "r", encoding="utf-8") as f:
                        self._symmetry_cfg = json.load(f)
                else:
                    print(f"[symmetry] config not found: {p}")
            except Exception as e:
                print(f"[symmetry] failed to load config: {e}")

    # --- 粗去重：基于谓词计数签名（不做谓词名规范化） ---
    def _signature_from_rule_text(self, rule_text: str) -> Optional[str]:
        """从规则文本生成“premise 谓词计数 + 结论谓词计数”的签名。
        不做大小写/别名规范化，仅使用解析到的谓词名原文；解析失败返回 None。
        例：prem:coll*1+eqangle*1+perp*2|concl:cong*1
        """
        try:
            if not isinstance(rule_text, str) or not rule_text.strip():
                return None
            left_parsed, right_parsed = _split_rule_text(rule_text)
            # 统计左侧谓词计数
            prem_counts: Dict[str, int] = {}
            for name, _ in left_parsed:
                if not name:
                    continue
                prem_counts[name] = prem_counts.get(name, 0) + 1
            # 统计右侧（允许多结论时的统一处理）
            concl_counts: Dict[str, int] = {}
            rn, _ = right_parsed
            if rn:
                concl_counts[rn] = concl_counts.get(rn, 0) + 1
            # 生成稳定签名（按名称字典序排序，区分大小写）
            prem_sig = "+".join([f"{k}*{prem_counts[k]}" for k in sorted(prem_counts.keys())]) if prem_counts else ""
            concl_sig = "+".join([f"{k}*{concl_counts[k]}" for k in sorted(concl_counts.keys())]) if concl_counts else ""
            return f"prem:{prem_sig}|concl:{concl_sig}"
        except Exception:
            return None

    def _dedup_by_signature(
        self, results: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[Tuple[str, str]]]]:
        """对结果按签名粗去重：同一签名仅保留首条，其余并入重复映射。
        返回：(保留后的 results, 重复映射 signature -> [(pid, rule_text), ...])。
        注意：重复映射包含该签名下的所有条目（含首条），便于审计输出。
        """
        seen: Dict[str, int] = {}
        kept: List[Dict[str, Any]] = []
        sig_groups: Dict[str, List[Tuple[str, str]]] = {}
        for rec in results:
            if not isinstance(rec, dict):
                continue
            rule = rec.get("proposition_rule")
            if not isinstance(rule, str) or not rule.strip():
                kept.append(rec)
                continue
            sig = self._signature_from_rule_text(rule)
            if not sig:
                kept.append(rec)
                continue
            pid = str(rec.get("problem_id", "<unknown>"))
            sig_groups.setdefault(sig, []).append((pid, rule))
            if sig not in seen:
                seen[sig] = 1
                kept.append(rec)
            else:
                # 后续重复样本不再加入 kept（仅记录于 sig_groups）
                seen[sig] += 1
        # 仅保留那些实际出现次数 > 1 的签名用于重复报告
        dup_map: Dict[str, List[Tuple[str, str]]] = {
            sig: lst for sig, lst in sig_groups.items() if len(lst) > 1
        }
        return kept, dup_map

    # 内部工具：收集有效且去重后的规则条目，绑定首个出现的 pid
    # 返回：entries（按编号顺序），skipped_count，skipped_entries
    def _collect_rules_entries(self, results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, List[Tuple[str, List[str], str]]]:
        seen: Dict[str, str] = {}
        ordered_norm: List[str] = []
        skipped = 0
        skipped_entries: List[Tuple[str, List[str], str]] = []  # (pid, missing_points, rule)
        norm_first_pid: Dict[str, str] = {}
        for rec in results:
            if not isinstance(rec, dict):
                continue
            rule = rec.get("proposition_rule")
            if not isinstance(rule, str) or not rule.strip():
                continue
            left_parsed, right_parsed = _split_rule_text(rule)
            left_points = _collect_point_set(left_parsed)
            right_points = set(_collect_point_list(right_parsed[1]))
            missing = right_points - left_points
            if missing:
                pid = rec.get("problem_id", "<unknown>")
                print(f"[rules] skip pid={pid} missing_points={sorted(missing)}")
                if self.print_skipped_rules:
                    # 打印被跳过的原始规则文本
                    print(f"[rules] skipped rule: {rule}")
                    skipped_entries.append((str(pid), sorted(missing), rule))
                skipped += 1
                continue
            # 先做点名重命名与基本规范，再结合谓词对称性生成稳定键
            norm = self._canonicalize_rule_with_symmetry(rule)
            if not norm:
                continue
            if norm not in seen:
                seen[norm] = rule
                ordered_norm.append(norm)
                # 记录首个出现该规范化规则的 pid
                pid_val = rec.get("problem_id", "<unknown>")
                norm_first_pid[norm] = str(pid_val)
        # 汇总 entries
        entries: List[Dict[str, Any]] = []
        for idx, norm in enumerate(ordered_norm):
            entries.append({
                "rid": _fmt_rule_id(idx),
                "norm_rule": norm,
                "rule": seen[norm],
                "pid": norm_first_pid.get(norm, "<unknown>"),
            })
        return entries, skipped, skipped_entries

    # --- 谓词对称性与规范化 ---
    def _normalize_clause_by_symmetry(self, pred: str, args: List[str]) -> Tuple[str, Tuple[str, ...]]:
        spec = self._symmetry_cfg.get(pred) if isinstance(self._symmetry_cfg, dict) else None
        if not spec or not isinstance(spec, dict):
            return pred, tuple(args)
        kind = spec.get("kind")
        if kind == "unordered":
            return pred, tuple(sorted(args))
        groups = spec.get("groups")
        allow_perm = bool(spec.get("allow_group_permutation", False))
        if kind in ("swap-pairs", "swap-groups") and isinstance(groups, list):
            # 切分为分组
            blocks: List[List[str]] = []
            try:
                for g in groups:
                    block = [args[i] for i in g if 0 <= i < len(args)]
                    # 组内排序
                    block.sort()
                    blocks.append(block)
            except Exception:
                return pred, tuple(args)
            # 组间排序（若允许）
            if allow_perm:
                blocks.sort(key=lambda b: ",".join(b))
            norm_args: List[str] = []
            for b in blocks:
                norm_args.extend(b)
            return pred, tuple(norm_args)
        return pred, tuple(args)

    def _canonicalize_rule_with_symmetry(self, rule_text: str) -> str:
        left_parsed, right_parsed = _split_rule_text(rule_text)
        # 收集点出现顺序并重命名（稳定）
        seq: List[str] = []

        def collect(args: Iterable[str]) -> None:
            for a in args:
                if _is_point_token(a) and a not in seq:
                    seq.append(a)

        for n, a in left_parsed:
            collect(a)
        collect(right_parsed[1])
        rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

        def map_args(args: List[str]) -> List[str]:
            return [rename.get(a, a) if _is_point_token(a) else a for a in args]

        # 子句级：先重命名，再按对称性规范化
        left_norm_clauses: List[Tuple[str, Tuple[str, ...]]] = []
        for n, a in left_parsed:
            if not n:
                continue
            mapped = map_args(a)
            left_norm_clauses.append(self._normalize_clause_by_symmetry(n, mapped))
        rn, ra = right_parsed
        right_norm_clause: Tuple[str, Tuple[str, ...]] = ("", tuple())
        if rn:
            right_norm_clause = self._normalize_clause_by_symmetry(rn, map_args(ra))

        # 前提子句排序（字典序），生成稳定文本
        left_texts = [f"{n} " + " ".join(a) if a else n for (n, a) in left_norm_clauses]
        left_texts.sort()
        right_text = f"{right_norm_clause[0]} " + " ".join(right_norm_clause[1]) if right_norm_clause[0] else ""
        if left_texts and right_text:
            return ", ".join(left_texts) + " => " + right_text
        if right_text:
            return "=> " + right_text
        return ", ".join(left_texts)

    # 分离：写规则文件（内部实现依赖规范化与过滤规则），并返回 entries
    def _write_rules_file(self, pruned_path: Path, results: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        # 先进行“谓词计数签名”的粗去重（默认启用）
        results_coarse, coarse_dup_map = self._dedup_by_signature(results)
        # 再进行现有的规则级规范化去重与收集
        entries, skipped, skipped_entries = self._collect_rules_entries(results_coarse)
        # 生成重复项清单（规范化键出现次数>1 的原始规则文本聚合）
        # 由于 _collect_rules_entries 只保留首个规范化规则，这里简单通过再次统计来获取重复项文本
        norm_dup_lines: List[str] = []
        coarse_dup_lines: List[str] = []
        try:
            norm_counter: Dict[str, List[Tuple[str, str]]] = {}
            for rec in results_coarse:
                rule = rec.get("proposition_rule")
                if not isinstance(rule, str) or not rule.strip():
                    continue
                norm = self._canonicalize_rule_with_symmetry(rule)
                if not norm:
                    continue
                pid = str(rec.get("problem_id", "<unknown>"))
                norm_counter.setdefault(norm, []).append((pid, rule))
            for norm, lst in norm_counter.items():
                if len(lst) > 1:
                    norm_dup_lines.append(f"norm={norm}")
                    for pid, rule in lst:
                        norm_dup_lines.append(f"  pid={pid} :: {rule}")
            # 追加粗去重的签名分组（signature）
            if coarse_dup_map:
                for sig, lst in coarse_dup_map.items():
                    coarse_dup_lines.append(f"signature={sig}")
                    for pid, rule in lst:
                        coarse_dup_lines.append(f"  pid={pid} :: {rule}")
        except Exception:
            norm_dup_lines = []
            coarse_dup_lines = []
        rules_path = pruned_path.with_name(pruned_path.stem + "_rules.txt")
        lines: List[str] = []
        for e in entries:
            lines.append(e["rid"])
            lines.append(e["rule"])
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        print(f"[rules] wrote {len(entries)} entries to {rules_path} (skipped={skipped})")

        # 写出 duplicated_rules.txt（若有）
        combined_dup_lines: List[str] = []
        if norm_dup_lines:
            combined_dup_lines.append("[norm] normalized duplicates")
            combined_dup_lines.extend(norm_dup_lines)
        if coarse_dup_lines:
            combined_dup_lines.append("[coarse] signature duplicates")
            combined_dup_lines.extend(coarse_dup_lines)
        if combined_dup_lines:
            dup_path = pruned_path.with_name(pruned_path.stem + "_duplicated_rules.txt")
            # 采用覆盖写（一次生成），与以往行为一致；包含 [norm] 与 [coarse] 两个分段
            with open(dup_path, "w", encoding="utf-8") as f:
                f.write("\n".join(combined_dup_lines) + "\n")
            print(f"[rules] duplicated list saved to {dup_path}")

        # 可选：将被跳过的规则另存，便于后续排查
        if self.print_skipped_rules and skipped_entries:
            skipped_path = pruned_path.with_name(pruned_path.stem + "_rules_skipped.txt")
            out_lines: List[str] = []
            for spid, miss, srule in skipped_entries:
                out_lines.append(f"pid={spid} missing_points={miss}")
                out_lines.append(srule)
            skipped_path.parent.mkdir(parents=True, exist_ok=True)
            with open(skipped_path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines) + ("\n" if out_lines else ""))
            print(f"[rules] skipped rules saved to {skipped_path}")
        return len(entries), skipped, entries

    def run(self, input_json: str | Path, output_dir: str | Path) -> Dict[str, Any]:
        in_path = Path(input_json)
        if not in_path.exists():
            raise FileNotFoundError(f"input not found: {in_path}")

        from newclid.data_discovery.aux_extractor import AuxExtractor

        normalized_obj = _normalize_input_object(in_path)
        src_results_all = normalized_obj.get("results", []) or []
        total_results = len(src_results_all)

        aux_extractor = AuxExtractor()
        aux_obj = aux_extractor.filter_results_obj(normalized_obj)
        src_results_aux = aux_obj.get("results", []) or []
        kept = len(src_results_aux)
        dropped = max(0, total_results - kept)
        print(f"[aux] filtered: total={total_results} kept={kept} dropped={dropped}")

        # 新增：基于(题干+aux)的去重，放在含 aux 筛选之后、修剪之前
        if kept > 0:
            src_results_dedup, dedup_stats = _dedup_by_question_and_aux(src_results_aux)
            if dedup_stats.get("removed", 0) > 0:
                print(f"[dedup] removed={dedup_stats['removed']} kept={dedup_stats['kept']}")
                if self.print_dedup_removed:
                    removed_ids = list(dedup_stats.get("removed_ids") or [])
                    if removed_ids:
                        print(f"[dedup] removed pids (first 20 shown): {removed_ids[:20]}{' ...' if len(removed_ids) > 20 else ''}")
        else:
            src_results_dedup, dedup_stats = [], {"removed": 0, "kept": 0}

        if len(src_results_dedup) <= 0:
            return {"total": total_results, "kept": 0, "dropped": dropped, "rendered": 0, "skipped": 0, "failed": 0}

        pids = [str(r.get("problem_id")) for r in src_results_dedup if isinstance(r, dict) and r.get("problem_id") is not None]

        pruned_map: Dict[str, Any] = {}
        mw = int(self.max_workers or 0)
        if mw > 1:
            print(f"[filter+prune] parallel pruning with max_workers={mw}")
            with ProcessPoolExecutor(max_workers=mw) as ex:
                futs = [ex.submit(_worker_prune, rec) for rec in src_results_dedup if isinstance(rec, dict) and rec.get("problem_id") is not None]
                for pid, rendered_one in (f.result() for f in as_completed(futs)):
                    if rendered_one:
                        pruned_map[pid] = rendered_one
        else:
            print("[filter+prune] sequential pruning")
            for rec in src_results_dedup:
                if not isinstance(rec, dict) or rec.get("problem_id") is None:
                    continue
                pid, rendered_one = _worker_prune(rec)
                if rendered_one:
                    pruned_map[pid] = rendered_one

        idx_src: Dict[str, Any] = {}
        for r in src_results_dedup:
            if isinstance(r, dict) and r.get("problem_id") is not None:
                idx_src[str(r["problem_id"])] = r

        out_results: List[Dict[str, Any]] = []
        for pid in pids:
            rendered = pruned_map.get(pid)
            if not rendered:
                continue
            base = {"problem_id": pid, "rendered": rendered}
            src = idx_src.get(pid, {})
            for k in ("aux_points", "point_lines", "points", "point_rely_on"):
                if k in src:
                    base[k] = src[k]
            if "aux_points" not in base and isinstance(src.get("aux_points"), list):
                base["aux_points"] = src["aux_points"]
            prop = _build_proposition_no_aux(rendered, list(base.get("aux_points", []) or []))
            if prop:
                base["proposition_no_aux"] = prop
                try:
                    rule_text, rename_map = _to_rule_text(prop.get("premises", []) or [], prop.get("conclusion", ""))
                    base["proposition_rule"] = rule_text
                    base["rename_map"] = rename_map
                    base["proposition_no_aux"]["rule_text"] = rule_text
                except Exception:
                    base["proposition_no_aux"].setdefault("rule_text", prop.get("text", ""))
            out_results.append(base)

        out_obj = {k: v for k, v in normalized_obj.items() if k != "results"}
        out_obj["results"] = out_results

        pruned_json = in_path.with_name(in_path.stem + "_pruned.json")
        with open(pruned_json, "w", encoding="utf-8") as f:
            json.dump(out_obj, f, ensure_ascii=False, indent=2)
        print(f"[filter+prune] pruned json written: {pruned_json}")

        n_rules, skipped_rules, rule_entries = self._write_rules_file(pruned_json, out_results)

        # 合并图渲染输出目录
        combo_stem = in_path.stem + "_aux"
        out_base_dir = Path(output_dir) / (combo_stem + "_combo")
        out_base_dir.mkdir(parents=True, exist_ok=True)
        print(f"[filter+prune] writing combined images to: {out_base_dir}")

        # 渲染：按 pid 的图片（可选，默认关闭）
        pid_done = pid_skipped = pid_failed = 0
        if self.keep_pid_images:
            total = len(pids)
            print(f"[filter+prune] start rendering by pid: total={total}")
            skipped_render_entries: List[Tuple[str, str]] = []  # (pid, reason)

            def submit_all(executor=None):
                tasks = []
                for pid in pids:
                    out_png = out_base_dir / f"proof_{pid}.png"
                    if out_png.exists() and not self.overwrite:
                        if self.print_render_skipped:
                            skipped_render_entries.append((pid, "exists_overwrite_false"))
                        yield (pid, "skipped")
                        continue
                    rendered = pruned_map.get(pid)
                    if not isinstance(rendered, dict):
                        if self.print_render_skipped:
                            skipped_render_entries.append((pid, "no_pruned_rendered"))
                        yield (pid, "skipped")
                        continue
                    rec = idx_src.get(pid)
                    if rec is None:
                        if self.print_render_skipped:
                            skipped_render_entries.append((pid, "no_source_record"))
                        yield (pid, "skipped")
                        continue
                    if executor is None:
                        yield _worker_render_combined(
                            rec,
                            rendered,
                            str(out_png),
                            self.label_mode,
                            self.figsize_single,
                            self.ranksep,
                            self.nodesep,
                            self.font_size,
                        )
                    else:
                        tasks.append(
                            executor.submit(
                                _worker_render_combined,
                                rec,
                                rendered,
                                str(out_png),
                                self.label_mode,
                                self.figsize_single,
                                self.ranksep,
                                self.nodesep,
                                self.font_size,
                            )
                        )
                if executor is not None:
                    for fut in as_completed(tasks):
                        yield fut.result()

            mw = int(self.max_workers or 0)
            if mw > 1:
                print(f"[filter+prune] parallel rendering by pid with max_workers={mw}")
                with ProcessPoolExecutor(max_workers=mw) as ex:
                    for idx, (pid, st) in enumerate(submit_all(ex), start=1):
                        if st == "ok":
                            pid_done += 1
                        elif st == "skipped":
                            pid_skipped += 1
                        else:
                            pid_failed += 1
                        if self.progress_every and (idx % self.progress_every == 0):
                            print(f"[filter+prune] (pid) {idx}/{len(pids)} done={pid_done} skipped={pid_skipped} failed={pid_failed}")
            else:
                print("[filter+prune] sequential rendering by pid")
                for idx, (pid, st) in enumerate(submit_all(None), start=1):
                    if st == "ok":
                        pid_done += 1
                    elif st == "skipped":
                        pid_skipped += 1
                    else:
                        pid_failed += 1
                    if self.progress_every and (idx % self.progress_every == 0):
                        print(f"[filter+prune] (pid) {idx}/{len(pids)} done={pid_done} skipped={pid_skipped} failed={pid_failed}")

            if self.print_render_skipped and (pid_skipped > 0):
                skipped_render_path = out_base_dir / "render_skipped.txt"
                with open(skipped_render_path, "w", encoding="utf-8") as f:
                    for spid, reason in skipped_render_entries:
                        f.write(f"pid={spid}\treason={reason}\n")
                print(f"[render] skipped list saved to {skipped_render_path}")

        # 渲染：按规则编号（默认开启）
        rid_done = rid_skipped = rid_failed = 0
        rid_total = len(rule_entries)
        if self.render_by_rule and rid_total > 0:
            print(f"[filter+prune] start rendering by rule: total={rid_total}")
            rid_skipped_entries: List[Tuple[str, str]] = []  # (rid, reason)

            def submit_rules_all(executor=None):
                tasks = []
                for e in rule_entries:
                    rid = str(e.get("rid"))
                    pid = str(e.get("pid"))
                    out_png = out_base_dir / f"{rid}.png"
                    if out_png.exists() and not self.overwrite:
                        if self.print_render_skipped:
                            rid_skipped_entries.append((rid, "exists_overwrite_false"))
                        yield (rid, "skipped")
                        continue
                    rendered = pruned_map.get(pid)
                    if not isinstance(rendered, dict):
                        if self.print_render_skipped:
                            rid_skipped_entries.append((rid, "no_pruned_rendered"))
                        yield (rid, "skipped")
                        continue
                    rec = idx_src.get(pid)
                    if rec is None:
                        if self.print_render_skipped:
                            rid_skipped_entries.append((rid, "no_source_record"))
                        yield (rid, "skipped")
                        continue
                    if executor is None:
                        yield _worker_render_combined(
                            rec,
                            rendered,
                            str(out_png),
                            self.label_mode,
                            self.figsize_single,
                            self.ranksep,
                            self.nodesep,
                            self.font_size,
                        )
                    else:
                        tasks.append(
                            executor.submit(
                                _worker_render_combined,
                                rec,
                                rendered,
                                str(out_png),
                                self.label_mode,
                                self.figsize_single,
                                self.ranksep,
                                self.nodesep,
                                self.font_size,
                            )
                        )
                if executor is not None:
                    for fut in as_completed(tasks):
                        yield fut.result()

            mw = int(self.max_workers or 0)
            if mw > 1:
                print(f"[filter+prune] parallel rendering by rule with max_workers={mw}")
                with ProcessPoolExecutor(max_workers=mw) as ex:
                    for idx, (rid, st) in enumerate(submit_rules_all(ex), start=1):
                        if st == "ok":
                            rid_done += 1
                        elif st == "skipped":
                            rid_skipped += 1
                        else:
                            rid_failed += 1
                        if self.progress_every and (idx % self.progress_every == 0):
                            print(f"[filter+prune] (rule) {idx}/{rid_total} done={rid_done} skipped={rid_skipped} failed={rid_failed}")
            else:
                print("[filter+prune] sequential rendering by rule")
                for idx, (rid, st) in enumerate(submit_rules_all(None), start=1):
                    if st == "ok":
                        rid_done += 1
                    elif st == "skipped":
                        rid_skipped += 1
                    else:
                        rid_failed += 1
                    if self.progress_every and (idx % self.progress_every == 0):
                        print(f"[filter+prune] (rule) {idx}/{rid_total} done={rid_done} skipped={rid_skipped} failed={rid_failed}")

            # 保存 rid_map.txt（rid -> pid 与规则文本）
            rid_map_path = out_base_dir / "rid_map.txt"
            with open(rid_map_path, "w", encoding="utf-8") as f:
                for e in rule_entries:
                    rid = str(e.get("rid"))
                    pid = str(e.get("pid"))
                    rule = str(e.get("rule"))
                    f.write(f"{rid} pid={pid} rule={rule}\n")
            print(f"[rules] rid_map saved to {rid_map_path}")

            if self.print_render_skipped and (rid_skipped > 0):
                rid_skipped_path = out_base_dir / "rid_render_skipped.txt"
                with open(rid_skipped_path, "w", encoding="utf-8") as f:
                    for rrid, reason in rid_skipped_entries:
                        f.write(f"rid={rrid}\treason={reason}\n")
                print(f"[render] rid skipped list saved to {rid_skipped_path}")

        # 总结输出
        print("-" * 30)
        print(f"Total problems: {len(pids)}")
        if self.keep_pid_images:
            print(f"Combined images (by pid): {pid_done}, Skipped: {pid_skipped}, Failed: {pid_failed}")
        print(f"Combined images (by rule): {rid_done}, Skipped: {rid_skipped}, Failed: {rid_failed}")
        print(f"Output directory: {out_base_dir}")
        print(f"JSON saved: {pruned_json}")

        # 保存去重被移除的 pid 列表
        if self.print_dedup_removed and (dedup_stats.get("removed_ids")):
            dedup_removed_path = out_base_dir / "dedup_removed.txt"
            with open(dedup_removed_path, "w", encoding="utf-8") as f:
                for spid in dedup_stats["removed_ids"]:
                    f.write(f"pid={spid}\n")
            print(f"[dedup] removed pid list saved to {dedup_removed_path}")

        # 导出 pid -> 输入题目文本 的映射（JSONL），便于按 pid 检索题目
        if self.save_pid_inputs and pids:
            pid_inputs_path = out_base_dir / "pid_inputs.jsonl"
            with open(pid_inputs_path, "w", encoding="utf-8") as f:
                for pid in pids:
                    src_rec = idx_src.get(pid, {})
                    llm_input = src_rec.get("llm_input_renamed", "") if isinstance(src_rec, dict) else ""
                    problem_body = _extract_tag_content(llm_input, "problem") or llm_input
                    problem_text = _norm_text_basic(problem_body)
                    json.dump({"pid": pid, "text": problem_text}, f, ensure_ascii=False)
                    f.write("\n")
            print(f"[pid-inputs] mapping saved to {pid_inputs_path}")

        return {
            "total": total_results,
            "kept": kept,
            "dropped": dropped,
            "rendered": (pid_done if self.keep_pid_images else 0) + rid_done,
            "skipped": (pid_skipped if self.keep_pid_images else 0) + rid_skipped,
            "failed": (pid_failed if self.keep_pid_images else 0) + rid_failed,
            "rules": n_rules,
            "skipped_rules": skipped_rules,
            "json": str(pruned_json),
            "images_dir": str(out_base_dir),
        }


__all__ = ["FilterAndPruneEngine"]


def _combine_pngs_h(left_png: Path, right_png: Path, out_png: Path, *, title: Optional[str] = None, subtitle: Optional[str] = None) -> str:
    """将两张 PNG 水平合并为一张，并在子图上方标注标题与副标题。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
    except Exception as e:
        raise RuntimeError(
            "缺少 matplotlib，无法进行合图保存。请安装 matplotlib 后重试。"
        ) from e

    img_l = mpimg.imread(str(left_png))
    img_r = mpimg.imread(str(right_png))

    fig, axes = plt.subplots(1, 2, figsize=(30, 20))
    axes[0].imshow(img_l)
    axes[0].axis("off")
    axes[0].set_title("Original", fontsize=10)

    axes[1].imshow(img_r)
    axes[1].axis("off")
    axes[1].set_title("Pruned", fontsize=10)

    if title:
        fig.suptitle(title, fontsize=12)
    if subtitle:
        sub = subtitle if len(subtitle) <= 220 else (subtitle[:217] + "...")
        fig.text(0.5, 0.015, "proposition w/o aux: " + sub, ha='center', va='bottom', fontsize=11, bbox=dict(boxstyle='round', fc='white', ec='#999999', alpha=0.85))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(str(out_png), dpi=200)
    plt.close(fig)
    return str(out_png)


def _parse_args_from_label(raw_label: str) -> List[str]:
    try:
        if "(" in raw_label and ")" in raw_label:
            inside = raw_label.split("(", 1)[1].rsplit(")", 1)[0]
            parts = [p.strip() for p in inside.split(",") if p.strip()]
            return parts
    except Exception:
        pass
    return []


def _is_point_token(tok: str) -> bool:
    if not tok:
        return False
    return re.match(r"^[A-Za-z][A-Za-z0-9_]*$", tok) is not None


def _alpha_seq(n: int) -> str:
    letters: List[str] = []
    while True:
        n, r = divmod(n, 26)
        letters.append(chr(ord('a') + r))
        if n == 0:
            break
        n -= 1
    return "".join(reversed(letters))


def _parse_name_args(raw_label: str) -> Tuple[str, List[str]]:
    name = raw_label
    args = _parse_args_from_label(raw_label)
    if "(" in raw_label:
        name = raw_label.split("(", 1)[0].strip()
    return name, args


def _to_rule_text(premises: List[str], conclusion: str) -> Tuple[str, Dict[str, str]]:
    seq: List[str] = []

    def _collect(args: List[str]):
        for a in args:
            if _is_point_token(a) and a not in seq:
                seq.append(a)

    parsed_prems: List[Tuple[str, List[str]]] = []
    for pl in premises:
        pn, pa = _parse_name_args(str(pl))
        parsed_prems.append((pn, pa))
        _collect(pa)
    cn, ca = _parse_name_args(str(conclusion))
    _collect(ca)

    rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

    def _fmt(name: str, args: List[str]) -> str:
        out: List[str] = []
        for a in args:
            if _is_point_token(a) and a in rename:
                out.append(rename[a])
            else:
                out.append(a)
        return name + (" " + " ".join(out) if out else "")

    prem_txts = [_fmt(n, a) for (n, a) in parsed_prems]
    concl_txt = _fmt(cn, ca)
    rule_text = (", ".join(prem_txts) + " => " + concl_txt) if prem_txts else ("=> " + concl_txt)
    return rule_text, rename


def _split_clauses(text: str) -> List[str]:
    parts = [p.strip() for p in (text or "").split(",")]
    return [p for p in parts if p]


def _parse_clause(clause: str) -> Tuple[str, List[str]]:
    tokens = [t for t in (clause or "").strip().split() if t]
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


def _split_rule_text(rule_text: str) -> Tuple[List[Tuple[str, List[str]]], Tuple[str, List[str]]]:
    if not isinstance(rule_text, str):
        return [], ("", [])
    if "=>" in rule_text:
        left, right = re.split(r"\s*=>\s*", rule_text.strip(), maxsplit=1)
    else:
        left, right = rule_text.strip(), ""
    left_parsed = [_parse_clause(c) for c in _split_clauses(left)] if left else []
    right_parsed = _parse_clause(right) if right else ("", [])
    return left_parsed, right_parsed


def _collect_point_set(clauses: Iterable[Tuple[str, List[str]]]) -> set[str]:
    points: set[str] = set()
    for _, args in clauses:
        for arg in args:
            if _is_point_token(arg):
                points.add(arg)
    return points


def _collect_point_list(args: Iterable[str]) -> List[str]:
    return [a for a in args if _is_point_token(a)]


def _canonicalize_rule_text(rule_text: str) -> str:
    left_parsed, right_parsed = _split_rule_text(rule_text)

    seq: List[str] = []

    def collect(args: Iterable[str]) -> None:
        for a in args:
            if _is_point_token(a) and a not in seq:
                seq.append(a)

    for _, args in left_parsed:
        collect(args)
    collect(right_parsed[1])

    rename: Dict[str, str] = {old: _alpha_seq(i) for i, old in enumerate(seq)}

    def fmt(name: str, args: List[str]) -> str:
        mapped = [rename.get(a, a) if _is_point_token(a) else a for a in args]
        return (name + (" " + " ".join(mapped) if mapped else "")).strip()

    left_norm = ", ".join([fmt(n, a) for n, a in left_parsed if n])
    right_norm = fmt(*right_parsed) if right_parsed[0] else ""
    if left_norm and right_norm:
        return f"{left_norm} => {right_norm}"
    if right_norm:
        return f"=> {right_norm}"
    return left_norm


def _fmt_rule_id(idx: int) -> str:
    return f"r{idx:04d}"


def _build_proposition_no_aux(rendered: Dict[str, Any], aux_points: List[str]) -> Optional[Dict[str, Any]]:
    nodes = (rendered or {}).get("nodes") or []
    edges = (rendered or {}).get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes:
        return None

    indeg = {n.get("idx"): 0 for n in nodes}
    outdeg = {n.get("idx"): 0 for n in nodes}
    for u, v in edges:
        outdeg[u] = outdeg.get(u, 0) + 1
        indeg[v] = indeg.get(v, 0) + 1

    fact_nodes = {n.get("idx"): n for n in nodes if n.get("type") == "fact"}
    premise_ids = [idx for idx, n in fact_nodes.items() if indeg.get(idx, 0) == 0]
    concl_ids = [idx for idx, n in fact_nodes.items() if outdeg.get(idx, 0) == 0]
    if len(concl_ids) != 1:
        return None

    aux_set = set(aux_points or [])
    kept_premises: List[str] = []
    for pid in premise_ids:
        raw_label = str(fact_nodes[pid].get("label", ""))
        args = _parse_args_from_label(raw_label)
        if not any(a in aux_set for a in args):
            kept_premises.append(raw_label)

    concl_label = str(fact_nodes[concl_ids[0]].get("label", ""))
    text = (", ".join(kept_premises) + " -> " + concl_label) if kept_premises else ("-> " + concl_label)
    return {"premises": kept_premises, "conclusion": concl_label, "text": text}


def _worker_prune(rec: Dict[str, Any]) -> Tuple[str, Any]:
    try:
        pid_val = rec.get("problem_id")
        if pid_val is None:
            return ("<none>", None)
        pid = str(pid_val)
        # 延迟导入，降低主进程依赖
        from newclid.data_discovery.graph_pruner import GraphPruner
        from newclid.data_discovery.single_proof_graph import SingleProofGraph
        pruner = GraphPruner()
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        rendered_one = pruner.prune_proof_graph(spg).get(pid)
        return (pid, rendered_one)
    except Exception:
        return (str(rec.get("problem_id")), None)


def _worker_render_combined(
    rec: Dict[str, Any],
    rendered: Dict[str, Any],
    out_png: str,
    label_mode: str,
    single_figsize: Tuple[int, int],
    ranksep: float,
    nodesep: float,
    font_size: int,
) -> Tuple[str, str]:
    try:
        from pathlib import Path as _Path
        import tempfile as _tempfile
        from newclid.data_discovery.proof_graph_visualizer import ProofGraphVisualizer
        from newclid.data_discovery.single_proof_graph import SingleProofGraph

        pid = str(rec.get("problem_id"))
        viz_left = ProofGraphVisualizer()
        viz_left.LAYOUT_RANKSEP = ranksep
        viz_left.LAYOUT_NODESEP = nodesep
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        with _tempfile.TemporaryDirectory() as td:
            td_path = _Path(td)
            left_png = td_path / f"left_{pid}.png"
            right_png = td_path / f"right_{pid}.png"
            viz_left.render_problem(spg, pid, str(left_png), label_mode=label_mode, highlight=True, figsize=single_figsize)
            # 修剪图（附 aux_points）
            rendered2 = dict(rendered)
            aux_points = rec.get("aux_points") or []
            if isinstance(aux_points, list):
                rendered2["aux_points"] = aux_points
            viz_right = ProofGraphVisualizer()
            viz_right.render_rendered(
                rendered2,
                str(right_png),
                label_mode=label_mode,
                highlight=True,
                figsize=single_figsize,
                font_size=font_size,
                show_direction_legend=True,
                layout_ranksep=ranksep,
                layout_nodesep=nodesep,
            )
            # 合图副标题优先使用规则文本
            prop = _build_proposition_no_aux(rendered2, list(rec.get("aux_points") or []))
            subtitle = None
            if isinstance(prop, dict):
                try:
                    rule_text, _ = _to_rule_text(prop.get("premises", []) or [], prop.get("conclusion", ""))
                    subtitle = rule_text
                except Exception:
                    subtitle = prop.get("text")
            _combine_pngs_h(left_png, right_png, _Path(out_png), title=f"Problem {pid}", subtitle=subtitle)
        return (pid, "ok")
    except Exception:
        return (str(rec.get("problem_id")), "failed")


