"""
Enhanced GRPO logging callback for diagnosing reward collapse.

Usage:
    Add to train_grpo.sh:
    --callbacks scripts/grpo/enhanced_logging_callback.py::EnhancedGRPOLogger
"""

import json
import os
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
from transformers import TrainerCallback, TrainerState, TrainerControl
from transformers.trainer_utils import PREFIX_CHECKPOINT_DIR


class EnhancedGRPOLogger(TrainerCallback):
    """
    Records per-step reward distribution details for collapse diagnosis.

    Outputs:
        {output_dir}/enhanced_reward_log.jsonl
            Per-step records with:
            - reward_distribution: histogram of reward values
            - group_stats: per-group (batch) statistics
            - status_breakdown: solved/unsolved/invalid counts
    """

    def __init__(self):
        self.log_file = None
        self.step_count = 0

    def on_train_begin(self, args, state, control, **kwargs):
        """Initialize log file."""
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = output_dir / "enhanced_reward_log.jsonl"

        # Write header
        with open(self.log_file, 'w') as f:
            f.write(json.dumps({
                "type": "header",
                "num_generations": getattr(args, 'num_generations', 8),
                "per_device_train_batch_size": args.per_device_train_batch_size,
                "gradient_accumulation_steps": args.gradient_accumulation_steps,
            }) + '\n')

    def on_log(self, args, state: TrainerState, control: TrainerControl, logs: Dict[str, float] = None, **kwargs):
        """
        Hook into logging to capture reward details.

        Note: This requires access to the trainer's internal state.
        If rewards are not in logs, you'll need to modify the GRPO trainer
        to expose per-sample rewards.
        """
        if logs is None or 'train/reward' not in logs:
            return

        self.step_count += 1

        # Try to extract detailed rewards from kwargs
        # This assumes the trainer passes 'model_outputs' or similar
        rewards = self._extract_rewards(kwargs)

        if rewards is None:
            # Fallback: only log aggregated stats
            record = {
                "step": self.step_count,
                "global_step": state.global_step,
                "reward_mean": logs.get('train/reward'),
                "reward_std": logs.get('train/reward_std'),
                "frac_zero_std": logs.get('train/frac_reward_zero_std'),
                "note": "detailed_rewards_not_available"
            }
        else:
            record = self._compute_detailed_stats(
                step=self.step_count,
                global_step=state.global_step,
                rewards=rewards,
                logs=logs
            )

        # Write to log
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def _extract_rewards(self, kwargs) -> List[float]:
        """
        Extract per-sample rewards from trainer kwargs.

        This is trainer-specific. You may need to modify based on
        how your GRPO trainer exposes rewards.
        """
        # Example: if trainer passes 'batch_rewards'
        if 'batch_rewards' in kwargs:
            return kwargs['batch_rewards']

        # Example: if in model_outputs
        if 'model_outputs' in kwargs:
            outputs = kwargs['model_outputs']
            if hasattr(outputs, 'rewards'):
                return outputs.rewards.cpu().numpy().tolist()

        return None

    def _compute_detailed_stats(
        self,
        step: int,
        global_step: int,
        rewards: List[float],
        logs: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute detailed reward distribution statistics."""
        rewards = np.array(rewards)

        # Overall distribution
        reward_hist = Counter(np.round(rewards, 2))

        # Group-level stats (assuming num_generations per problem)
        num_gens = 8  # TODO: get from args
        num_problems = len(rewards) // num_gens

        group_stats = []
        for i in range(num_problems):
            group_rewards = rewards[i * num_gens : (i + 1) * num_gens]
            unique_vals, counts = np.unique(group_rewards, return_counts=True)

            group_stats.append({
                "unique_count": len(unique_vals),
                "top1_ratio": counts.max() / num_gens,
                "entropy": self._entropy(counts),
                "std": float(np.std(group_rewards)),
                "mean": float(np.mean(group_rewards)),
            })

        # Aggregate group stats
        zero_std_groups = sum(1 for g in group_stats if g['std'] == 0)
        high_concentration_groups = sum(1 for g in group_stats if g['top1_ratio'] >= 0.875)

        return {
            "step": step,
            "global_step": global_step,

            # Aggregated (from logs)
            "reward_mean": logs.get('train/reward'),
            "reward_std": logs.get('train/reward_std'),
            "frac_zero_std": logs.get('train/frac_reward_zero_std'),

            # Distribution
            "reward_histogram": dict(reward_hist.most_common(10)),
            "reward_min": float(rewards.min()),
            "reward_max": float(rewards.max()),
            "reward_median": float(np.median(rewards)),

            # Group-level
            "num_groups": num_problems,
            "zero_std_groups": zero_std_groups,
            "high_concentration_groups": high_concentration_groups,
            "avg_group_unique_count": np.mean([g['unique_count'] for g in group_stats]),
            "avg_group_entropy": np.mean([g['entropy'] for g in group_stats]),

            # Top concentrated values
            "top_reward_values": [
                {"value": float(k), "count": int(v)}
                for k, v in reward_hist.most_common(5)
            ],
        }

    @staticmethod
    def _entropy(counts: np.ndarray) -> float:
        """Compute Shannon entropy of a distribution."""
        probs = counts / counts.sum()
        return float(-np.sum(probs * np.log2(probs + 1e-10)))


# Analysis script
def analyze_enhanced_log(log_path: str):
    """
    Analyze enhanced_reward_log.jsonl to diagnose collapse.

    Usage:
        python enhanced_logging_callback.py /path/to/enhanced_reward_log.jsonl
    """
    import matplotlib.pyplot as plt

    records = []
    with open(log_path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get('type') != 'header':
                records.append(rec)

    steps = [r['step'] for r in records]

    # Plot 1: Reward concentration over time
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # 1a: Zero-std groups
    axes[0, 0].plot(steps, [r['zero_std_groups'] for r in records])
    axes[0, 0].set_title('Zero-Std Groups per Step')
    axes[0, 0].set_xlabel('Step')
    axes[0, 0].set_ylabel('Count')

    # 1b: Average group entropy
    axes[0, 1].plot(steps, [r['avg_group_entropy'] for r in records])
    axes[0, 1].set_title('Avg Group Entropy')
    axes[0, 1].set_xlabel('Step')
    axes[0, 1].set_ylabel('Entropy (bits)')

    # 1c: Reward std
    axes[1, 0].plot(steps, [r['reward_std'] for r in records])
    axes[1, 0].set_title('Reward Std')
    axes[1, 0].set_xlabel('Step')
    axes[1, 0].set_ylabel('Std')

    # 1d: High concentration groups
    axes[1, 1].plot(steps, [r['high_concentration_groups'] for r in records])
    axes[1, 1].set_title('High Concentration Groups (top1≥87.5%)')
    axes[1, 1].set_xlabel('Step')
    axes[1, 1].set_ylabel('Count')

    plt.tight_layout()
    plt.savefig(log_path.replace('.jsonl', '_analysis.png'))
    print(f"Saved analysis to {log_path.replace('.jsonl', '_analysis.png')}")

    # Print summary
    print("\n=== Collapse Diagnosis ===")

    # Find collapse point
    collapse_threshold = 0.7
    collapse_steps = [
        r['step'] for r in records
        if r['zero_std_groups'] / r['num_groups'] > collapse_threshold
    ]

    if collapse_steps:
        first_collapse = min(collapse_steps)
        print(f"First collapse at step {first_collapse}")

        # Analyze what rewards dominate at collapse
        collapse_rec = next(r for r in records if r['step'] == first_collapse)
        print(f"\nTop reward values at collapse:")
        for item in collapse_rec['top_reward_values']:
            print(f"  {item['value']:+.2f}: {item['count']} samples")
    else:
        print("No collapse detected")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        analyze_enhanced_log(sys.argv[1])
    else:
        print("Usage: python enhanced_logging_callback.py <log_path>")
