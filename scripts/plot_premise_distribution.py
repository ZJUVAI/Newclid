#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate premise count distribution bar charts before and after filtering."""

import json
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter

# Allow specifying experiment directory via command line
exp_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs/experiments/20260309_10k_rule_extraction_no_eqpoint_constline'

# Load data (try step6 first, fallback to step1e for backward compatibility)
import os
step6_path = f'{exp_dir}/intermediates/step6_rules_stats.json'
step1e_path = f'{exp_dir}/intermediates/step1e_rules_stats.json'

if os.path.exists(step6_path):
    data = json.load(open(step6_path))
elif os.path.exists(step1e_path):
    data = json.load(open(step1e_path))
else:
    raise FileNotFoundError(f"Neither {step6_path} nor {step1e_path} found")

entries = data['entries']

# Count premises before and after filtering
before_counts = Counter()
after_counts = Counter()

unsupported_predicates = {'constline', 'eqpoint'}
unsupported_rules = {'r107', 'r108', 'constline', 'eqpoint'}

for e in entries:
    rule = e.get('rule', '')
    if '=>' not in rule:
        continue

    # Count premises
    n_prem = len([c for c in rule.split('=>')[0].split(',') if c.strip()])
    before_counts[n_prem] += 1

    # Check filters
    if n_prem > 10:
        continue

    rule_lower = rule.lower()
    has_unsupported = any(pred in rule_lower for pred in unsupported_predicates) or \
                      any(r in rule_lower for r in unsupported_rules)

    if has_unsupported:
        continue

    after_counts[n_prem] += 1

# Prepare data for plotting
max_prem = max(before_counts.keys())
x = list(range(2, max_prem + 1))
before_y = [before_counts.get(i, 0) for i in x]
after_y = [after_counts.get(i, 0) for i in x]

# Create figure with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Plot 1: Before filtering
ax1.bar(x, before_y, color='steelblue', alpha=0.7, edgecolor='black')
ax1.axvline(x=10, color='red', linestyle='--', linewidth=2, label='max_premises=10')
ax1.set_xlabel('Number of Premises', fontsize=12)
ax1.set_ylabel('Count', fontsize=12)
ax1.set_title('Before Filtering (Total: {} rules)'.format(sum(before_y)), fontsize=14, fontweight='bold')
ax1.legend()
ax1.grid(axis='y', alpha=0.3)

# Plot 2: After filtering
ax2.bar(x[:9], after_y[:9], color='green', alpha=0.7, edgecolor='black')
ax2.set_xlabel('Number of Premises', fontsize=12)
ax2.set_ylabel('Count', fontsize=12)
ax2.set_title('After Filtering (Total: {} rules, max_premises=10, no unsupported)'.format(sum(after_y)),
              fontsize=14, fontweight='bold')
ax2.grid(axis='y', alpha=0.3)
ax2.set_xlim(1.5, 10.5)

plt.tight_layout()
output_png = f'{exp_dir}/premise_count_distribution.png'
plt.savefig(output_png, dpi=150, bbox_inches='tight')
print(f'Saved: {output_png}')

# Print statistics
print('\n=== Statistics ===')
print(f'Before filtering: {sum(before_y)} rules')
print(f'After filtering: {sum(after_y)} rules')
print(f'Filtered out: {sum(before_y) - sum(after_y)} rules ({(sum(before_y) - sum(after_y))/sum(before_y)*100:.1f}%)')
print(f'\nPremise distribution (after filtering):')
for i in range(2, 11):
    if after_counts[i] > 0:
        print(f'  {i:2d} premises: {after_counts[i]:4d} ({after_counts[i]/sum(after_y)*100:5.1f}%)')
