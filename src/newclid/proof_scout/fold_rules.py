#!/usr/bin/env python3
"""
规则折叠脚本

将具有相同前提的多条规则折叠为一条规则，合并其结论。

算法：
1. 加载规则文件（两行一组：规则名+规则内容）
2. 解析每条规则，提取前提部分和结论部分（以 ` => ` 分隔）
3. 对前提部分进行标准化处理（按字母顺序排序各谓词），作为分组键
4. 将具有相同标准化前提的规则分组
5. 对于每组规则：
   - 保留第一条规则的规则名
   - 将所有规则的结论用 `, ` 连接合并
   - 生成折叠后的规则：`{原前提} => {结论1}, {结论2}, ...`
6. 输出折叠后的规则文件

用法:
    python fold_rules.py [--input <输入文件>] [--output <输出文件>]
"""

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict

# ==================== 配置参数（在此处修改） ====================

# 输入规则文件路径
INPUT_RULES_FILE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/c10s200k/rules_minimal.txt"

# 输出折叠后规则文件路径
OUTPUT_FOLDED_FILE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/c10s200k/rules_folded.txt"

# ==================== 配置参数结束 ====================


@dataclass
class Rule:
    """表示一条规则"""
    name: str           # 规则名称
    premises: str       # 原始前提字符串
    conclusion: str     # 结论字符串
    normalized_key: str # 标准化后的前提（用于分组）


def normalize_premises(premises_str: str) -> str:
    """
    标准化前提字符串：按字典序排序各谓词
    
    Args:
        premises_str: 原始前提字符串，如 "cong a b c b, midp d e f, para a e f c"
        
    Returns:
        排序后的前提字符串
    """
    # 按逗号分割各谓词
    predicates = [p.strip() for p in premises_str.split(',')]
    # 按字典序排序
    predicates.sort()
    # 重新用逗号连接
    return ', '.join(predicates)


def parse_rule(name: str, content: str) -> Rule:
    """
    解析规则内容
    
    Args:
        name: 规则名称
        content: 规则内容，格式为 "前提 => 结论"
        
    Returns:
        Rule 对象
    """
    # 按 " => " 分割前提和结论
    parts = content.split(' => ')
    if len(parts) != 2:
        raise ValueError(f"规则格式错误，无法找到 ' => ' 分隔符: {content}")
    
    premises = parts[0].strip()
    conclusion = parts[1].strip()
    normalized_key = normalize_premises(premises)
    
    return Rule(
        name=name,
        premises=premises,
        conclusion=conclusion,
        normalized_key=normalized_key
    )


def load_rules(filepath: str) -> List[Rule]:
    """
    加载规则文件（两行一组：规则名+规则内容）
    
    Args:
        filepath: 规则文件路径
        
    Returns:
        规则列表
    """
    rules = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 两行一组解析
    i = 0
    while i < len(lines) - 1:
        name = lines[i].strip()
        content = lines[i + 1].strip()
        
        if name and content:
            try:
                rule = parse_rule(name, content)
                rules.append(rule)
            except ValueError as e:
                print(f"警告: 跳过规则 {name}: {e}")
        
        i += 2
    
    return rules


def fold_rules(rules: List[Rule]) -> List[Tuple[str, str, str]]:
    """
    折叠具有相同前提的规则
    
    Args:
        rules: 规则列表
        
    Returns:
        折叠后的规则列表，每个元素为 (规则名, 原始前提, 合并后的结论)
    """
    # 使用 OrderedDict 保持规则的原始顺序
    groups: Dict[str, List[Rule]] = OrderedDict()
    
    for rule in rules:
        key = rule.normalized_key
        if key not in groups:
            groups[key] = []
        groups[key].append(rule)
    
    # 折叠每组规则
    folded = []
    for key, group in groups.items():
        # 保留第一条规则的名称和原始前提
        first_rule = group[0]
        name = first_rule.name
        premises = first_rule.premises
        
        # 收集所有结论（去重，保持顺序）
        conclusions = []
        seen_conclusions = set()
        for rule in group:
            if rule.conclusion not in seen_conclusions:
                conclusions.append(rule.conclusion)
                seen_conclusions.add(rule.conclusion)
        
        # 合并结论
        merged_conclusion = ', '.join(conclusions)
        
        folded.append((name, premises, merged_conclusion))
    
    return folded


def save_folded_rules(folded: List[Tuple[str, str, str]], filepath: str) -> None:
    """
    保存折叠后的规则文件
    
    Args:
        folded: 折叠后的规则列表
        filepath: 输出文件路径
    """
    # 确保输出目录存在
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for name, premises, conclusion in folded:
            f.write(f"{name}\n")
            f.write(f"{premises} => {conclusion}\n")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='将具有相同前提的多条规则折叠为一条规则，合并其结论'
    )
    parser.add_argument(
        '--input',
        type=str,
        default=INPUT_RULES_FILE,
        help=f'输入规则文件路径 (默认: {INPUT_RULES_FILE})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=OUTPUT_FOLDED_FILE,
        help=f'输出折叠后规则文件路径 (默认: {OUTPUT_FOLDED_FILE})'
    )
    
    args = parser.parse_args()
    
    input_file = args.input
    output_file = args.output
    
    print("=" * 60)
    print("规则折叠脚本")
    print("=" * 60)
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print()
    
    # 加载规则
    print("正在加载规则...")
    rules = load_rules(input_file)
    original_count = len(rules)
    print(f"加载了 {original_count} 条规则")
    print()
    
    # 折叠规则
    print("正在折叠规则...")
    folded = fold_rules(rules)
    folded_count = len(folded)
    print(f"折叠后剩余 {folded_count} 条规则")
    print()
    
    # 保存结果
    print("正在保存结果...")
    save_folded_rules(folded, output_file)
    print(f"结果已保存到: {output_file}")
    print()
    
    # 统计信息
    print("=" * 60)
    print("统计信息")
    print("=" * 60)
    print(f"原始规则数: {original_count}")
    print(f"折叠后规则数: {folded_count}")
    print(f"合并比例: {100 * (1 - folded_count / original_count):.2f}%")
    
    # 显示合并了多条结论的规则数量
    multi_conclusion_count = sum(1 for _, _, c in folded if ', ' in c)
    print(f"包含多个结论的规则数: {multi_conclusion_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
