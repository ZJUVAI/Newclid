#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Divide-and-Conquer Rule Reducer.

Replaces the old Chunk Reduction + Global Reduction with a unified two-phase approach:

  Phase 1 (Initial Chunking):
      Split rules into chunks, reduce each chunk independently via Ray tasks.
      Each chunk's internal rules become mutually non-subsuming.

  Phase 2 (Merge Reduction):
      Merge chunks pairwise until one chunk remains.
      Each merge tests cross-chunk subsumption using fine-grained Ray tasks
      coordinated through a Ray Actor for shared mutable state.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import ray

from newclid.proof_scout.reduction.ray_workers import (
    merge_two_chunks_ray,
    reduce_chunk_worker_ray,
    serialize_rule,
)


@dataclass
class ChunkMeta:
    """Metadata for a chunk of rules (stores only IDs, not full objects)."""
    chunk_id: int
    rule_ids: List[str] = field(default_factory=list)


class DivideConquerReducer:
    """Divide-and-conquer rule reduction using Ray.

    Phase 1: Split rules into chunks, reduce each chunk independently.
    Phase 2: Merge chunks pairwise until one chunk remains.
    """

    def __init__(
        self,
        timeout: int = 60,
        seed: int = 42,
        solver_type: str = "csolver",
        engine: str = "full",
        min_chunk_size: int = 50,
        n_workers: int = 50,
        batch_size: int = 10,
        verbose: bool = True,
        output_dir: Optional[Path] = None,
    ):
        self.timeout = timeout
        self.seed = seed
        self.solver_type = solver_type
        self.engine = engine
        self.min_chunk_size = max(1, min_chunk_size)
        self.n_workers = max(1, n_workers)
        self.batch_size = batch_size
        self.verbose = verbose
        self.output_dir = Path(output_dir) if output_dir else None

        self.global_rules_dict: Dict[str, Any] = {}
        self.eliminated_rules: List[Dict[str, Any]] = []
        self.phase1_stats: List[Dict[str, Any]] = []
        self.phase2_stats: List[Dict[str, Any]] = []
        self._merge_counter = 0
        self._next_chunk_id = 0

        # Progress tracking
        self._phase1_total = 0
        self._phase1_completed = 0
        self._phase2_total = 0
        self._phase2_completed = 0
        self._last_phase1_progress_pct = 0
        self._last_phase2_progress_pct = 0
        self._phase1_start_time: Optional[float] = None
        self._phase2_start_time: Optional[float] = None
        self._input_count = 0

    def reduce(self, rules: List[Any]) -> Dict[str, Any]:
        """Main entry point for divide-and-conquer reduction."""
        start_time = time.time()
        self.global_rules_dict = {rule.rule_id: rule for rule in rules}
        self.eliminated_rules = []
        self.phase1_stats = []
        self.phase2_stats = []
        self._merge_counter = 0
        self._next_chunk_id = 0

        if self.output_dir:
            (self.output_dir / "phase1_chunks").mkdir(parents=True, exist_ok=True)
            (self.output_dir / "phase2_merges").mkdir(parents=True, exist_ok=True)

        if not rules:
            stats = {
                "input_count": 0,
                "basis_count": 0,
                "eliminated_count": 0,
                "reduction_rate": 0.0,
                "phase1": {"n_chunks": 0, "chunk_size": 0, "elapsed_seconds": 0.0},
                "phase2": {"n_merges": 0, "elapsed_seconds": 0.0},
                "n_subsumption_tests": 0,
                "elapsed_seconds": 0.0,
            }
            self._save_final_stats(stats)
            return {
                "basis_rules": [],
                "eliminated_rules": [],
                "stats": stats,
            }

        if self.verbose:
            print(f"[DivideConquerReducer] Starting with {len(rules)} rules")

        final_chunk, phase1_elapsed, phase2_elapsed = self._pipelined_reduce(rules)

        basis_rules = [self.global_rules_dict[rid] for rid in final_chunk.rule_ids]
        total_tests = sum(item.get("n_subsumption_tests", 0) for item in self.phase1_stats)
        total_tests += sum(item.get("n_subsumption_tests", 0) for item in self.phase2_stats)
        total_elapsed = time.time() - start_time

        stats = {
            "input_count": len(rules),
            "basis_count": len(basis_rules),
            "eliminated_count": len(rules) - len(basis_rules),
            "reduction_rate": (len(rules) - len(basis_rules)) / len(rules) if rules else 0.0,
            "phase1": {
                "n_chunks": len(self.phase1_stats),
                "chunk_size": self._compute_chunk_size(len(rules)),
                "elapsed_seconds": round(phase1_elapsed, 2),
                "chunk_details": self.phase1_stats,
            },
            "phase2": {
                "n_merges": len(self.phase2_stats),
                "elapsed_seconds": round(phase2_elapsed, 2),
                "merge_details": self.phase2_stats,
            },
            "n_subsumption_tests": total_tests,
            "elapsed_seconds": round(total_elapsed, 2),
        }

        self._save_final_stats(stats)

        if self.verbose:
            reduction_pct = (len(rules) - len(basis_rules)) / len(rules) * 100 if rules else 0.0
            print(
                f"[DivideConquerReducer] Done: {len(rules)} → {len(basis_rules)} rules "
                f"({total_elapsed:.1f}s, {reduction_pct:.1f}% reduction)"
            )

        return {
            "basis_rules": basis_rules,
            "eliminated_rules": self.eliminated_rules,
            "stats": stats,
        }

    def _compute_chunk_size(self, n_rules: int) -> int:
        """Compute chunk size ensuring n_chunks >= n_workers so every worker gets a chunk."""
        ideal = max(1, (n_rules + self.n_workers - 1) // self.n_workers)
        return min(self.min_chunk_size, ideal)

    def _allocate_chunk_id(self) -> int:
        chunk_id = self._next_chunk_id
        self._next_chunk_id += 1
        return chunk_id

    def _pipelined_reduce(self, rules: List[Any]) -> tuple[ChunkMeta, float, float]:
        """Pipelined Phase 1 and Phase 2 reduction.

        Returns:
            (final_chunk, phase1_elapsed, phase2_elapsed)
        """
        if not rules:
            return ChunkMeta(chunk_id=self._allocate_chunk_id(), rule_ids=[]), 0.0, 0.0

        # Initialize progress tracking
        self._input_count = len(rules)
        chunk_size = self._compute_chunk_size(len(rules))
        chunks_data = [rules[i:i + chunk_size] for i in range(0, len(rules), chunk_size)]

        self._phase1_total = len(chunks_data)
        self._phase2_total = len(chunks_data) - 1  # n chunks → n-1 merges
        self._phase1_completed = 0
        self._phase2_completed = 0
        self._last_phase1_progress_pct = 0
        self._last_phase2_progress_pct = 0

        if self.verbose:
            print(f"[Phase 1] Submitting {len(chunks_data)} chunks (size={chunk_size})")

        # Submit all Phase 1 tasks upfront
        phase1_remaining = []
        for idx, chunk_rules in enumerate(chunks_data):
            future = reduce_chunk_worker_ray.remote(
                idx, chunk_rules, self.timeout, self.seed, self.batch_size,
                self.solver_type, self.engine, self.verbose
            )
            phase1_remaining.append((idx, len(chunk_rules), future))

        merge_queue: List[ChunkMeta] = []
        active_merge_future = None
        active_merge_info = None  # (chunk_A, chunk_B, merge_id)

        phase1_start = time.time()
        self._phase1_start_time = phase1_start
        phase1_end = None
        phase2_start = None
        phase2_end = None

        while phase1_remaining or len(merge_queue) > 1 or active_merge_future is not None:
            something_ready = False

            # 1. Non-blocking check: any Phase 1 chunk done?
            if phase1_remaining:
                refs = [ref for _, _, ref in phase1_remaining]
                done, _ = ray.wait(refs, num_returns=1, timeout=0)
                if done:
                    something_ready = True
                    done_ref = done[0]
                    # Find which chunk completed
                    for i, (chunk_idx, input_count, ref) in enumerate(phase1_remaining):
                        if ref == done_ref:
                            result = ray.get(done_ref)
                            chunk_meta = self._process_phase1_result(chunk_idx, input_count, result)
                            merge_queue.append(chunk_meta)
                            phase1_remaining.pop(i)

                            # Update progress
                            self._phase1_completed += 1
                            self._log_phase1_progress(merge_queue)
                            break

                    # Mark Phase 1 end when last chunk completes
                    if not phase1_remaining and phase1_end is None:
                        phase1_end = time.time()

            # 2. Non-blocking check: active merge done?
            if active_merge_future is not None:
                done, _ = ray.wait([active_merge_future], timeout=0)
                if done:
                    something_ready = True
                    result = ray.get(active_merge_future)
                    chunk_A, chunk_B, merge_id = active_merge_info
                    merged_chunk = self._process_merge_result(chunk_A, chunk_B, merge_id, result)
                    merge_queue.append(merged_chunk)
                    active_merge_future = None
                    active_merge_info = None

                    # Update progress
                    self._phase2_completed += 1
                    self._log_phase2_progress(merge_queue)

            # 3. Start new merge if idle and queue >= 2
            if active_merge_future is None and len(merge_queue) >= 2:
                chunk_A = merge_queue.pop(0)
                chunk_B = merge_queue.pop(0)
                merge_id = self._merge_counter
                self._merge_counter += 1

                if phase2_start is None:
                    phase2_start = time.time()
                    self._phase2_start_time = phase2_start
                    if self.verbose:
                        print("[Phase 2] Started (2 chunks ready for merge)")

                active_merge_future = self._submit_merge_task(chunk_A, chunk_B)
                active_merge_info = (chunk_A, chunk_B, merge_id)

            # 4. Block until any event if nothing was ready
            if not something_ready:
                all_refs = [ref for _, _, ref in phase1_remaining]
                if active_merge_future is not None:
                    all_refs.append(active_merge_future)
                if all_refs:
                    ray.wait(all_refs, num_returns=1)

        # Mark Phase 2 end
        if phase2_start is not None:
            phase2_end = time.time()

        # Handle edge cases
        if phase1_end is None:
            phase1_end = time.time()
        if phase2_start is None:
            phase2_start = phase1_end
        if phase2_end is None:
            phase2_end = phase2_start

        phase1_elapsed = phase1_end - phase1_start
        phase2_elapsed = phase2_end - phase2_start

        final_chunk = merge_queue[0] if merge_queue else ChunkMeta(chunk_id=self._allocate_chunk_id(), rule_ids=[])
        return final_chunk, phase1_elapsed, phase2_elapsed

    def _process_phase1_result(self, chunk_idx: int, input_count: int, result: Dict[str, Any]) -> ChunkMeta:
        """Process Phase 1 chunk reduction result."""
        basis_rules = result.get("basis_rules", [])
        eliminated_rules = result.get("eliminated_rules", [])
        stats = result.get("stats", {})

        # Extract rule IDs
        basis_rule_ids = [r.rule_id for r in basis_rules]

        # Record eliminated rules
        for elim_entry in eliminated_rules:
            self.eliminated_rules.append({
                "rule_id": elim_entry["rule_id"],
                "eliminated_by": "phase1_chunk",
                "chunk_id": chunk_idx,
                "subsumed_by": elim_entry.get("subsumed_by"),
            })

        # Save stats
        chunk_stats = {
            "chunk_id": chunk_idx,
            "input_count": input_count,
            "basis_count": len(basis_rule_ids),
            "eliminated_count": len(eliminated_rules),
            "n_subsumption_tests": stats.get("n_subsumption_tests", 0),
            "elapsed_seconds": result.get("time", 0),
            "basis_rule_ids": basis_rule_ids,
        }
        self.phase1_stats.append(chunk_stats)
        self._save_phase1_chunk(chunk_stats)

        return ChunkMeta(chunk_id=self._allocate_chunk_id(), rule_ids=basis_rule_ids)

    def _submit_merge_task(self, chunk_A: ChunkMeta, chunk_B: ChunkMeta):
        """Submit a merge task to Ray."""
        rules_a_data = [serialize_rule(self.global_rules_dict[rid]) for rid in chunk_A.rule_ids]
        rules_b_data = [serialize_rule(self.global_rules_dict[rid]) for rid in chunk_B.rule_ids]

        return merge_two_chunks_ray.remote(
            rules_a_data,
            rules_b_data,
            self.timeout,
            self.seed,
            self.solver_type,
            self.engine,
            self.batch_size,
        )

    def _process_merge_result(
        self, chunk_A: ChunkMeta, chunk_B: ChunkMeta, merge_id: int, result: Dict[str, Any]
    ) -> ChunkMeta:
        """Process Phase 2 merge result."""
        active_a = result["active_a"]
        active_b = result["active_b"]
        n_tests_step1 = result["n_tests_step1"]
        n_tests_step2 = result["n_tests_step2"]
        elapsed_seconds = result.get("elapsed_seconds", 0)

        rules_a_ids = chunk_A.rule_ids
        rules_b_ids = chunk_B.rule_ids

        # Collect eliminated rules
        eliminated_a = [rules_a_ids[i] for i, active in enumerate(active_a) if not active]
        eliminated_b = [rules_b_ids[i] for i, active in enumerate(active_b) if not active]

        for rid in eliminated_a:
            self.eliminated_rules.append({
                "rule_id": rid,
                "eliminated_by": "phase2_merge",
                "merge_id": merge_id,
                "eliminated_from": "chunk_a",
            })
        for rid in eliminated_b:
            self.eliminated_rules.append({
                "rule_id": rid,
                "eliminated_by": "phase2_merge",
                "merge_id": merge_id,
                "eliminated_from": "chunk_b",
            })

        # Merged rule IDs
        merged_rule_ids = [rules_a_ids[i] for i, active in enumerate(active_a) if active]
        merged_rule_ids += [rules_b_ids[i] for i, active in enumerate(active_b) if active]

        # Save stats
        merge_stats = {
            "merge_id": merge_id,
            "chunk_a_id": chunk_A.chunk_id,
            "chunk_b_id": chunk_B.chunk_id,
            "input_a_count": len(rules_a_ids),
            "input_b_count": len(rules_b_ids),
            "surviving_a_count": sum(active_a),
            "surviving_b_count": sum(active_b),
            "basis_count": len(merged_rule_ids),
            "eliminated_a_count": len(eliminated_a),
            "eliminated_b_count": len(eliminated_b),
            "n_subsumption_tests": n_tests_step1 + n_tests_step2,
            "step1_tests": n_tests_step1,
            "step2_tests": n_tests_step2,
            "elapsed_seconds": elapsed_seconds,
            "merged_rule_ids": merged_rule_ids,
        }
        self.phase2_stats.append(merge_stats)
        self._save_phase2_merge(merge_stats)

        return ChunkMeta(chunk_id=self._allocate_chunk_id(), rule_ids=merged_rule_ids)

    def _save_phase1_chunk(self, chunk_stats: Dict[str, Any]) -> None:
        if not self.output_dir:
            return
        out_path = self.output_dir / "phase1_chunks" / f"chunk_{chunk_stats['chunk_id']:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(chunk_stats, f, ensure_ascii=False, indent=2)

    def _save_phase2_merge(self, merge_stats: Dict[str, Any]) -> None:
        if not self.output_dir:
            return
        out_path = self.output_dir / "phase2_merges" / f"merge_{merge_stats['merge_id']:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merge_stats, f, ensure_ascii=False, indent=2)

    def _save_final_stats(self, stats: Dict[str, Any]) -> None:
        if not self.output_dir:
            return
        out_path = self.output_dir / "final_stats.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    def _log_phase1_progress(self, merge_queue: List[ChunkMeta]) -> None:
        """Log Phase 1 progress at 10% intervals."""
        if not self.verbose:
            return

        pct = int(100 * self._phase1_completed / self._phase1_total)
        # Log at 10% intervals or when complete
        if pct >= self._last_phase1_progress_pct + 10 or self._phase1_completed == self._phase1_total:
            # Calculate reduced rules: input - current basis
            current_basis = sum(len(c.rule_ids) for c in merge_queue)
            reduced = self._input_count - current_basis
            elapsed = time.time() - self._phase1_start_time

            if self._phase1_completed == self._phase1_total:
                print(f"[Phase 1] ✓ Complete: {self._phase1_completed}/{self._phase1_total} chunks | "
                      f"Reduced: {reduced} rules | Elapsed: {elapsed:.1f}s")
            else:
                print(f"[Phase 1] Progress: {self._phase1_completed}/{self._phase1_total} chunks "
                      f"({pct:.1f}%) | Reduced: {reduced} rules | Elapsed: {elapsed:.1f}s")

            self._last_phase1_progress_pct = pct

    def _log_phase2_progress(self, merge_queue: List[ChunkMeta]) -> None:
        """Log Phase 2 progress at 10% intervals with ETA."""
        if not self.verbose:
            return

        pct = int(100 * self._phase2_completed / self._phase2_total)
        # Log at 10% intervals or when complete
        if pct >= self._last_phase2_progress_pct + 10 or self._phase2_completed == self._phase2_total:
            # Calculate reduced rules
            current_basis = sum(len(c.rule_ids) for c in merge_queue)
            reduced = self._input_count - current_basis

            # Calculate elapsed and ETA
            elapsed = time.time() - self._phase2_start_time

            if self._phase2_completed == self._phase2_total:
                print(f"[Phase 2] ✓ Complete: {self._phase2_completed}/{self._phase2_total} merges | "
                      f"Reduced: {reduced} rules | Elapsed: {elapsed:.1f}s")
            else:
                print(f"[Phase 2] Progress: {self._phase2_completed}/{self._phase2_total} merges "
                      f"({pct:.1f}%) | Reduced: {reduced} rules | Elapsed: {elapsed:.1f}s")

            self._last_phase2_progress_pct = pct
