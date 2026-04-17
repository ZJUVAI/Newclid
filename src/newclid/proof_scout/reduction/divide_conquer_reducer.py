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
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import ray

from newclid.proof_scout.reduction.ray_workers import (
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

        phase1_start = time.time()
        chunks = self._phase1_initial_chunking(rules)
        phase1_elapsed = time.time() - phase1_start

        phase2_start = time.time()
        if not chunks:
            final_chunk = ChunkMeta(chunk_id=self._allocate_chunk_id(), rule_ids=[])
        elif len(chunks) == 1:
            final_chunk = chunks[0]
        else:
            final_chunk = self._phase2_merge_reduction(chunks)
        phase2_elapsed = time.time() - phase2_start

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
                "n_chunks": len(chunks),
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
            print(
                f"[DivideConquerReducer] Done: {len(rules)} → {len(basis_rules)} rules "
                f"({total_elapsed:.1f}s)"
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

    def _phase1_initial_chunking(self, rules: List[Any]) -> List[ChunkMeta]:
        """Split rules into chunks and reduce each chunk independently."""
        chunk_size = self._compute_chunk_size(len(rules))
        chunks = [
            rules[i:i + chunk_size]
            for i in range(0, len(rules), chunk_size)
        ]

        if self.verbose:
            print(
                f"[DivideConquerReducer/Phase1] {len(rules)} rules → {len(chunks)} chunks "
                f"(chunk_size={chunk_size})"
            )

        futures = []
        for chunk_idx, chunk_rules in enumerate(chunks):
            future = reduce_chunk_worker_ray.remote(
                chunk_idx,
                chunk_rules,
                self.timeout,
                self.seed,
                self.batch_size,
                self.solver_type,
                self.engine,
                self.verbose,
            )
            futures.append((chunk_idx, len(chunk_rules), future))

        phase1_chunks: List[ChunkMeta] = []
        remaining = list(futures)
        while remaining:
            ready_refs = [ref for _, _, ref in remaining]
            done, _ = ray.wait(ready_refs, num_returns=1)
            done_ref = done[0]

            for idx, (chunk_idx, input_count, ref) in enumerate(remaining):
                if ref != done_ref:
                    continue
                remaining.pop(idx)
                result = ray.get(done_ref)
                basis_rules = result.get("basis_rules", [])
                basis_ids = [rule.rule_id for rule in basis_rules]
                phase1_chunks.append(ChunkMeta(chunk_id=chunk_idx, rule_ids=basis_ids))
                self.eliminated_rules.extend(result.get("eliminated_rules", []))

                chunk_stats = {
                    "chunk_id": chunk_idx,
                    "input_count": input_count,
                    "basis_count": len(basis_ids),
                    "eliminated_count": input_count - len(basis_ids),
                    "n_subsumption_tests": result.get("stats", {}).get("n_subsumption_tests", 0),
                    "elapsed_seconds": round(result.get("time", 0), 2),
                    "rule_ids": basis_ids,
                }
                self.phase1_stats.append(chunk_stats)
                self._save_phase1_chunk(chunk_stats)
                break

        phase1_chunks.sort(key=lambda chunk: chunk.chunk_id)
        self.phase1_stats.sort(key=lambda item: item["chunk_id"])
        self._next_chunk_id = max((chunk.chunk_id for chunk in phase1_chunks), default=-1) + 1
        return phase1_chunks

    def _phase2_merge_reduction(self, chunks: List[ChunkMeta]) -> ChunkMeta:
        """Merge chunks pairwise until one chunk remains."""
        merge_queue = list(chunks)

        if self.verbose:
            print(f"[DivideConquerReducer/Phase2] Starting with {len(merge_queue)} chunks")

        while len(merge_queue) > 1:
            chunk_a = merge_queue.pop(0)
            chunk_b = merge_queue.pop(0)
            merged_chunk = self._merge_two_chunks(chunk_a, chunk_b)
            merge_queue.append(merged_chunk)

            if self.verbose:
                print(
                    f"[DivideConquerReducer/Phase2] Queue size: {len(merge_queue)} "
                    f"after merge {self._merge_counter}"
                )

        return merge_queue[0]

    def _merge_two_chunks(self, chunk_a: ChunkMeta, chunk_b: ChunkMeta) -> ChunkMeta:
        """Merge two already-reduced chunks."""
        from newclid.proof_scout.reduction.ray_workers import (
            ActiveStateActor,
            test_and_update_worker_ray,
        )

        self._merge_counter += 1
        merge_id = self._merge_counter

        rules_a = [self.global_rules_dict[rid] for rid in chunk_a.rule_ids]
        rules_b = [self.global_rules_dict[rid] for rid in chunk_b.rule_ids]
        rules_a_data = [serialize_rule(rule) for rule in rules_a]
        rules_b_data = [serialize_rule(rule) for rule in rules_b]

        if self.verbose:
            print(
                f"[DivideConquerReducer/merge {merge_id}] "
                f"chunk {chunk_a.chunk_id} ({len(rules_a)}) + "
                f"chunk {chunk_b.chunk_id} ({len(rules_b)})"
            )

        merge_start = time.time()
        actor = ActiveStateActor.remote(len(rules_a), len(rules_b))

        futures_step1 = [
            test_and_update_worker_ray.remote(
                rule_a_data,
                rules_b_data,
                actor,
                "B",
                self.timeout,
                self.seed,
                self.solver_type,
                self.engine,
            )
            for rule_a_data in rules_a_data
        ]
        ray.get(futures_step1)
        active_b = ray.get(actor.get_active_B.remote())

        surviving_b_indices = [idx for idx, is_active in enumerate(active_b) if is_active]
        surviving_b_data = [rules_b_data[idx] for idx in surviving_b_indices]
        futures_step2 = [
            test_and_update_worker_ray.remote(
                rule_b_data,
                rules_a_data,
                actor,
                "A",
                self.timeout,
                self.seed,
                self.solver_type,
                self.engine,
            )
            for rule_b_data in surviving_b_data
        ]
        if futures_step2:
            ray.get(futures_step2)

        active_a = ray.get(actor.get_active_A.remote())
        active_b = ray.get(actor.get_active_B.remote())

        merged_rule_ids = [
            chunk_a.rule_ids[idx]
            for idx, is_active in enumerate(active_a)
            if is_active
        ]
        merged_rule_ids.extend(
            chunk_b.rule_ids[idx]
            for idx, is_active in enumerate(active_b)
            if is_active
        )

        eliminated_a = [chunk_a.rule_ids[idx] for idx, is_active in enumerate(active_a) if not is_active]
        eliminated_b = [chunk_b.rule_ids[idx] for idx, is_active in enumerate(active_b) if not is_active]
        for rule_id in eliminated_a:
            self.eliminated_rules.append({
                "rule_id": rule_id,
                "rule_text": self.global_rules_dict[rule_id].rule_text,
                "subsumed_by": f"merge_{merge_id}",
                "reason": f"Eliminated during merge {merge_id} against chunk {chunk_b.chunk_id}",
            })
        for rule_id in eliminated_b:
            self.eliminated_rules.append({
                "rule_id": rule_id,
                "rule_text": self.global_rules_dict[rule_id].rule_text,
                "subsumed_by": f"merge_{merge_id}",
                "reason": f"Eliminated during merge {merge_id} against chunk {chunk_a.chunk_id}",
            })

        n_tests_step1 = len(rules_a) * len(rules_b)
        n_tests_step2 = len(surviving_b_indices) * len(rules_a)
        merge_stats = {
            "merge_id": merge_id,
            "chunk_a_id": chunk_a.chunk_id,
            "chunk_b_id": chunk_b.chunk_id,
            "input_a_count": len(rules_a),
            "input_b_count": len(rules_b),
            "surviving_a_count": sum(active_a),
            "surviving_b_count": sum(active_b),
            "basis_count": len(merged_rule_ids),
            "eliminated_a_count": len(eliminated_a),
            "eliminated_b_count": len(eliminated_b),
            "n_subsumption_tests": n_tests_step1 + n_tests_step2,
            "step1_tests": n_tests_step1,
            "step2_tests": n_tests_step2,
            "elapsed_seconds": round(time.time() - merge_start, 2),
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
