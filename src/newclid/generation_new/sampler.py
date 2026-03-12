"""
ClauseDAG-based problem sampler for geometric constructions.

This module provides a DAG-based approach to managing geometric clauses,
with ClauseDAG as the core data structure for tracking dependencies
and enabling efficient pruning.
"""

from __future__ import annotations

import logging
import random
import re
from typing import Union

import numpy

from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import Clause, translate_sentence
from newclid.statement import Statement
from newclid.configs import default_defs_path
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.numerical.sketch import sketch
from newclid.numerical.geometries import ObjNum, PointNum, reduce
from newclid.numerical.distances import (
    PointTooCloseError,
    PointTooFarError,
    check_too_far_numerical,
    check_too_close_numerical,
)

from newclid.generation_new.point_naming import PointNaming
from newclid.generation_new.constructions import resolve_construction_config
from newclid.generation_new.auxiliary import add_potential_points

MAX_TRY = 10


class ClauseNode:
    """
    A node in the ClauseDAG representing a single clause.

    Tracks the clause's points, construction dependencies, and relationships
    to other nodes in the DAG.
    """

    def __init__(self, clause: Clause):
        """
        Initialize a ClauseNode.

        Args:
            clause: The Clause object this node represents.
        """
        self.clause = clause
        self.points = self._extract_point_names()
        self.construction_deps = self._extract_construction_deps()
        self.rely_on_points = set().union(*self.construction_deps) if self.construction_deps else set()
        self.children: list[ClauseNode] = []
        self.parents: list[ClauseNode] = []
        self.depth: int = 0

    def _extract_point_names(self) -> set[str]:
        """Extract point names (without coordinates) from clause points."""
        return {p.split('@')[0] for p in self.clause.points}

    def _extract_construction_deps(self) -> list[set[str]]:
        """
        Extract dependency points for each construction in the clause.

        Returns:
            List of sets, where each set contains the dependency points
            for the corresponding construction sentence.
        """
        deps = []
        for sentence in self.clause.sentences:
            if not sentence:
                deps.append(set())
                continue
            # Extract point names from sentence arguments (skip construction name)
            sentence_points = {s for s in sentence[1:] if s and s[0].isalpha() and not s[0].isdigit()}
            # Filter out angle values like "45o"
            sentence_points = {p for p in sentence_points if not p.endswith('o')}
            # Dependency points are those not defined by this clause
            dep_points = sentence_points - self.points
            deps.append(dep_points)
        return deps


class ClauseDAG:
    """
    Directed Acyclic Graph for managing geometric clauses.

    Tracks clause dependencies, enables topological sorting, and provides
    pruning functionality to keep only the deepest construction chains.
    """

    def __init__(self):
        """Initialize an empty ClauseDAG."""
        self.nodes: list[ClauseNode] = []
        self.point_to_node: dict[str, ClauseNode] = {}
        self.point_coords: dict[str, tuple[float, float]] = {}

    def add_clause(self, clause: Clause) -> ClauseNode:
        """
        Add a clause to the DAG.

        Establishes parent-child relationships based on point dependencies
        and computes the node's depth in the DAG.

        Args:
            clause: The Clause to add.

        Returns:
            The created ClauseNode.
        """
        node = ClauseNode(clause)

        # Build parent-child relationships
        parent_nodes = set()
        for dep_point in node.rely_on_points:
            if dep_point in self.point_to_node:
                parent_nodes.add(self.point_to_node[dep_point])

        for parent in parent_nodes:
            parent.children.append(node)
            node.parents.append(parent)

        # Compute depth (max parent depth + 1)
        node.depth = max((p.depth for p in node.parents), default=-1) + 1

        # Extract coordinates and update point mappings
        for p in clause.points:
            point_name = p.split('@')[0]
            if '@' in p:
                parts = p.split('@')
                try:
                    if len(parts) >= 2 and '_' in parts[1]:
                        # Format: name@x_y
                        x_str, y_str = parts[1].split('_')
                        self.point_coords[point_name] = (float(x_str), float(y_str))
                    elif len(parts) >= 3:
                        # Format: name@x@y
                        self.point_coords[point_name] = (float(parts[1]), float(parts[2]))
                except (ValueError, IndexError):
                    pass
            self.point_to_node[point_name] = node

        self.nodes.append(node)
        return node

    def prune(self, topk: int = 1) -> None:
        """
        Prune the DAG to keep only the deepest k layers of leaf nodes and their ancestors.

        This removes branches that don't contribute to the deepest construction
        chains, simplifying the problem while preserving the most complex paths.

        Args:
            topk: Number of deepest layers to keep (default 1, i.e., only the deepest layer).
        """
        if not self.nodes:
            return

        # Find maximum depth
        max_depth = max(node.depth for node in self.nodes)
        min_keep_depth = max(0, max_depth - topk + 1)

        # Find leaf nodes in the top k layers (depth >= min_keep_depth)
        target_leaves = [
            n for n in self.nodes
            if n.depth >= min_keep_depth and not n.children
        ]

        if not target_leaves:
            # If no leaves in target range, pick random nodes from target depth range
            target_nodes = [n for n in self.nodes if n.depth >= min_keep_depth]
            if target_nodes:
                target_leaves = [random.choice(target_nodes)]
            else:
                return

        # Collect nodes to keep (target leaves + all ancestors)
        keep_nodes: set[ClauseNode] = set()

        def collect_ancestors(node: ClauseNode) -> None:
            if node in keep_nodes:
                return
            keep_nodes.add(node)
            for parent in node.parents:
                collect_ancestors(parent)

        for leaf in target_leaves:
            collect_ancestors(leaf)

        # Find points to remove
        removed_points: set[str] = set()
        for node in self.nodes:
            if node not in keep_nodes:
                removed_points.update(node.points)

        # Update data structures
        self.nodes = [n for n in self.nodes if n in keep_nodes]
        for point in removed_points:
            self.point_to_node.pop(point, None)
            self.point_coords.pop(point, None)

        # Clean up children references
        for node in self.nodes:
            node.children = [c for c in node.children if c in keep_nodes]

    def add_auxiliary_points(self, max_points: int = 2, point_naming: PointNaming = None) -> None:
        """
        Add potential auxiliary points to the DAG.

        Finds meaningful geometric points (intersections, midpoints, reflections, feet)
        and adds them as new clauses to the DAG.

        Args:
            max_points: Maximum number of auxiliary points to add.
            point_naming: PointNaming instance for generating new point names.
                         If None, creates a new instance.
        """
        if not self.nodes or not self.point_coords:
            return

        if point_naming is None:
            point_naming = PointNaming()
            # Pre-define existing points
            for p in sorted(self.point_to_node.keys()):
                point_naming.define_points([p])

        # Use the DAG's coordinate data directly
        point_names = list(self.point_coords.keys())
        coords = self.point_coords.copy()

        # Call the new add_potential_points function
        potential_points = add_potential_points(point_names, coords, max_points)

        # Directly create Clause and add to DAG
        for coord, constructions in potential_points:
            new_name = point_naming.prefetch_points(1)[0]
            point_naming.define_points([new_name])

            # Build Clause
            point_with_coord = f"{new_name}@{coord[0]}_{coord[1]}"
            sentences = tuple(
                tuple([ctype, new_name] + args) for ctype, args in constructions
            )
            clause = Clause((point_with_coord,), sentences)
            self.add_clause(clause)

    def get_all_points(self) -> set[str]:
        """Get all point names in the DAG."""
        return set(self.point_to_node.keys())

    def get_max_depth(self) -> int:
        """Get the maximum depth of any node in the DAG."""
        if not self.nodes:
            return -1
        return max(node.depth for node in self.nodes)

    def _topological_sort(self) -> list[ClauseNode]:
        """
        Perform topological sort on the DAG.

        Nodes are sorted so that dependencies come first, with ties broken
        by depth (shallower first), then lexicographic order of point names,
        then number of dependencies (fewer first).

        Returns:
            List of ClauseNodes in topological order.
        """
        result = []
        defined_points: set[str] = set()
        remaining = set(self.nodes)

        while remaining:
            # Find nodes whose dependencies are satisfied
            ready = [n for n in remaining if n.rely_on_points <= defined_points]
            if not ready:
                # Circular dependency (shouldn't happen)
                break

            # Sort by: 1) depth (shallower first), 2) min point name, 3) number of dependencies
            ready.sort(key=lambda n: (n.depth, min(n.points), len(n.rely_on_points)))

            # Take the first ready node
            node = ready[0]
            result.append(node)
            defined_points.update(node.points)
            remaining.remove(node)

        return result

    def to_problem(self, with_coords: bool = False, rename: bool = True) -> str:
        """
        Convert the DAG to a problem string.

        Performs topological sort, optionally renames points to standard names (a, b, c, ...),
        and formats the output.

        Args:
            with_coords: Whether to include coordinate information.
            rename: Whether to rename points using PointNaming convention.

        Returns:
            Problem string with clauses separated by semicolons.
        """
        if not self.nodes:
            return ""

        # Topological sort
        sorted_nodes = self._topological_sort()

        # Build point renaming map
        old_to_new: dict[str, str] = {}
        if rename:
            point_naming = PointNaming()
            for node in sorted_nodes:
                for p in sorted(node.points):
                    if p not in old_to_new:
                        new_names = point_naming.prefetch_points(1)
                        point_naming.define_points(new_names)
                        old_to_new[p] = new_names[0]
        else:
            # Identity mapping (no renaming)
            for node in sorted_nodes:
                for p in node.points:
                    old_to_new[p] = p

        # Generate output
        clause_strs = []
        for node in sorted_nodes:
            renamed_clause = node.clause.renamed(old_to_new)
            if with_coords:
                clause_strs.append(str(renamed_clause))
            else:
                # Remove coordinates from points
                points_str = ' '.join(old_to_new[p] for p in sorted(node.points))
                sentences_str = ', '.join(' '.join(s) for s in renamed_clause.sentences)
                clause_strs.append(f"{points_str} = {sentences_str}")

        return '; '.join(clause_strs)


class ProblemSampler:
    """
    Sampler for geometric problems using ClauseDAG.

    Samples geometric constructions by combining basic shapes, intersections,
    and other construction types, managing them through a DAG structure.
    """

    def __init__(
        self,
        seed: int = None,
        defs: dict = None,
        construction_config: dict | None = None,
    ):
        """
        Initialize the problem sampler.

        Args:
            seed: Random seed for reproducibility.
            defs: Definition dictionary. If None, loads from default path.
            construction_config: Optional external config defining the
                construction sets and the three sampler steps.
        """
        self.construction_defs = defs or DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_txt_file(default_defs_path())
        )
        resolved_profile = resolve_construction_config(
            construction_config=construction_config,
            available_constructions=set(self.construction_defs.keys()),
        )
        self.rng = numpy.random.default_rng(seed)
        random.seed(seed)
        self.point_naming: PointNaming = None
        self.symbols_graph = None
        self.dep_graph: DependencyGraph = None
        self.dag: ClauseDAG = None
        self.construction_config = construction_config
        self.step1_pool = resolved_profile["step1_pool"]
        self.step2_pool = resolved_profile["step2_pool"]
        self.step3_pool = resolved_profile["step3_pool"]

    def generate(
        self,
        length: int = 0,
        add_auxiliary: bool = True,
        max_auxiliary_points: int = 2,
        prune: bool = True,
        prune_topk: int = 1,
        with_coords: bool = True,
        rename: bool = True
    ) -> str:
        """
        Generate geometric clauses.

        Args:
            length: Number of clause sets to generate.
            add_auxiliary: Whether to add auxiliary points using enhancement.
            prune: Whether to prune clauses to preserve only the deepest chains.
            prune_topk: Number of deepest layers to keep when pruning (default 1).
            with_coords: Whether to include coordinate information in output.
            rename: Whether to rename points to standard names (a, b, c, ...).

        Returns:
            A string of generated clauses separated by semicolons.
        """
        self.point_naming = PointNaming()
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.symbols_graph = self.dep_graph.symbols_graph
        self.dag = ClauseDAG()

        # Step 1: Sample initial clauses
        for clause_set in range(length):
            if clause_set == 0:
                new_clause_strs = self._sample_clauses(
                    construction_type_candidates=self.step1_pool,
                    num_construction_types=1,
                    num_clauses=1,
                )
            else:
                if random.random() < 0.5:
                    new_clause_strs = self._sample_clauses(
                        construction_type_candidates=self.step2_pool,
                        num_construction_types=2,
                        num_clauses=2,
                        num_points=1,
                    )
                else:
                    new_clause_strs = self._sample_clauses(
                        construction_type_candidates=self.step3_pool,
                        num_construction_types=1,
                        num_clauses=1,
                    )

            # Parse clause strings and add to DAG
            for clause_str in new_clause_strs:
                clause = self._parse_clause_str(clause_str)
                self.dag.add_clause(clause)

        # Step 2: Prune to keep deepest chains
        if prune:
            self.dag.prune(topk=prune_topk)

        # Step 3: Add auxiliary points
        if add_auxiliary:
            self.dag.add_auxiliary_points(max_points=max_auxiliary_points, point_naming=self.point_naming)

        # Step 4: Convert to problem string
        return self.dag.to_problem(with_coords=with_coords, rename=rename)

    def _parse_clause_str(self, clause_str: str) -> Clause:
        """
        Parse a clause string into a Clause object.

        Args:
            clause_str: String in format "a@x_y b@x_y = construction1 args, construction2 args"

        Returns:
            Parsed Clause object.
        """
        parts = clause_str.split('=')
        if len(parts) != 2:
            raise ValueError(f"Invalid clause string: {clause_str}")

        points_part, constructions_part = parts
        points = tuple(points_part.strip().split())

        sentences = []
        for c in constructions_part.strip().split(','):
            tokens = c.strip().split()
            if tokens:
                sentences.append(tuple(tokens))

        return Clause(points, tuple(sentences))

    def _sample_clauses(
        self,
        construction_type_candidates: list[str],
        num_construction_types: int,
        num_clauses: int,
        num_points: int = None,
    ) -> list[str]:
        """
        Sample clauses using specified construction type candidates.

        Args:
            construction_type_candidates: List of candidate construction types.
            num_construction_types: Number of construction types to use per clause.
            num_clauses: Number of clauses to generate.
            num_points: Number of new points to generate (optional).

        Returns:
            A list of generated clause strings.
        """
        num_points_backup = num_points
        for _ in range(MAX_TRY):
            try:
                # Select construction types and map arguments
                (
                    selected_construction_types,
                    args_mappings,
                    numeric_list,
                    construction_points,
                    num_points
                ) = self._select_construction_types(
                    construction_type_candidates,
                    num_construction_types,
                    num_points_backup,
                )

                if len(selected_construction_types) != num_construction_types:
                    continue

                try:
                    clause_strs = self._build_clause_strings(
                        selected_construction_types,
                        args_mappings,
                        numeric_list,
                        construction_points,
                        num_clauses,
                        num_points,
                    )
                except Exception as e:
                    logging.debug(f"Clause application failed: {e}")
                    continue

                return clause_strs

            except Exception as e:
                logging.debug(f"Clause generation attempt failed: {e}")
                continue
        return []

    def _select_construction_types(
        self,
        construction_type_candidates: list[str],
        num_construction_types: int,
        num_points: int,
    ) -> tuple[list[str], list[dict[str, str]], list[tuple], set[Point], int]:
        """
        Select construction types and map their arguments.

        Returns:
            A tuple of (selected_construction_types, args_mappings, numeric_list,
            construction_points, num_points).
        """
        selected_construction_types: list[str] = []
        args_mappings: list[dict[str, str]] = []
        numeric_list: list[tuple] = []
        construction_points: set[Point] = set()

        for _ in range(num_construction_types):
            random_construction_type_candidates = construction_type_candidates.copy()
            self.rng.shuffle(random_construction_type_candidates)

            for construction in random_construction_type_candidates:
                construction_def = self.construction_defs[construction]

                if num_points is None:
                    num_points = len(construction_def.points)
                elif len(construction_def.points) != num_points:
                    continue

                if len(construction_def.args) > len(self.point_naming.defined_points):
                    continue

                args_mapping = self._map_construction_args(
                    construction_def,
                    self.point_naming.defined_points,
                )
                if not self._validate_construction_requirements(construction_def, args_mapping):
                    continue

                numerics = self._extract_numerics(construction_def, args_mapping)
                new_construction_points = self._extract_construction_points(
                    construction_def, args_mapping
                )

                selected_construction_types.append(construction)
                args_mappings.append(args_mapping)
                numeric_list.extend(numerics)
                construction_points.update(new_construction_points)
                break

        return selected_construction_types, args_mappings, numeric_list, construction_points, num_points

    def _build_clause_strings(
        self,
        selected_construction_types: list[str],
        args_mappings: list[dict[str, str]],
        numeric_list: list[tuple],
        construction_points: set[Point],
        num_clauses: int,
        num_points: int,
    ) -> list[str]:
        """Build clause strings from selected construction types."""
        clause_strs: list[str] = []

        for i in range(num_clauses):
            try:
                new_points = self.point_naming.prefetch_points(num_points)
                # Check numerics by drawing diagram
                self._draw_diagram(new_points, numeric_list, construction_points)
                self.point_naming.define_points(new_points)

                construction_strs: list[str] = []
                for construction, mapping in zip(selected_construction_types, args_mappings):
                    mapping.update(
                        dict(zip(self.construction_defs[construction].points, new_points)))
                    construction_strs.append(
                        self._format_construction_text(self.construction_defs[construction], mapping)
                    )
                    self._validate_construction_basics(self.construction_defs[construction], mapping)

                new_point_strs = self._format_points_with_coords(new_points)
                clause_str = ' '.join(new_point_strs) + " = " + ', '.join(construction_strs)
                clause_strs.append(clause_str)

            except Exception as e:
                if i == 0:
                    raise e
                else:
                    logging.debug(f"Multiple clause generation attempt failed: {e}")
                    break

        return clause_strs

    def _validate_construction_requirements(self, construction_def, mapping) -> bool:
        """Validate construction requirements (premises)."""
        try:
            for premise in construction_def.require.sentences:
                if len(premise) == 0:
                    continue
                statement = Statement.from_tokens(
                    translate_sentence(mapping, premise), self.dep_graph)
                if statement is None or not statement.check_numerical():
                    return False
            return True
        except Exception as e:
            logging.debug(f"Requirement validation failed: {e}")
            return False

    def _validate_construction_basics(self, construction_def, mapping) -> bool:
        """Validate construction basic properties."""
        try:
            for basic_statement in construction_def.basics:
                for t in basic_statement.sentences:
                    Statement.from_tokens(
                        translate_sentence(mapping, t), self.dep_graph)
            return True
        except Exception as e:
            logging.warning(f"Error processing construction basics: {e}")
            return False

    def _extract_numerics(self, construction_def, mapping) -> list:
        """Extract numerical constraints from construction definition."""
        numerics = []
        for n in construction_def.numerics:
            numerics.append(
                tuple(mapping[a] if a in mapping else a for a in n))
        return numerics

    def _extract_construction_points(self, construction_def, mapping) -> set[Point]:
        """Extract construction points from construction definition."""
        construction_points = set()
        for arg in construction_def.args:
            if mapping[arg] in self.symbols_graph.name2node:
                construction_points.add(self.symbols_graph.name2node[mapping[arg]])
        return construction_points

    def _format_points_with_coords(self, point_names: list[str]) -> list[str]:
        """Format point names with their coordinates."""
        points = self.symbols_graph.names2points(point_names)
        return [f'{p.name}@{p.num.x}_{p.num.y}' for p in points]

    def _draw_diagram(self, new_points: list[str], numerics: list, construction_points: set[Point]):
        """Draw diagram and validate point positions."""
        def draw_fn() -> tuple[PointNum, ...]:
            to_be_intersected: list[ObjNum] = []
            for n in numerics:
                args: list[Union[PointNum, str]] = []
                for t in n[1:]:
                    if str.isalpha(t[0]):
                        args.append(self.symbols_graph.names2points([t])[0].num)
                    else:
                        args.append(t)
                to_be_intersected += sketch(n[0], tuple(args), self.rng)

            return reduce(
                to_be_intersected,
                [p.num for p in _existing_points],
                [p.num for p in construction_points],
                rng=self.rng,
            )

        _existing_points = list(self.symbols_graph.nodes_of_type(Point))
        _existing_points = [p for p in _existing_points if hasattr(p, "num")]
        _new_points = self.symbols_graph.names2points(new_points)
        _new_numerical_point = draw_fn()

        if len(_new_numerical_point) != len(_new_points):
            raise Exception("Point count mismatch in draw result")

        # Check point distances
        _existing_numerical_points = [p.num for p in _existing_points]
        if check_too_close_numerical(_new_numerical_point, _existing_numerical_points, round=-1.0):
            raise PointTooCloseError()
        if check_too_far_numerical(_new_numerical_point, _existing_numerical_points):
            raise PointTooFarError()

        # Set point positions
        for p, num in zip(_new_points, _new_numerical_point):
            p.num = num

    def _map_construction_args(
        self,
        construction_def: DefinitionJGEX,
        defined_points: list[str],
    ) -> dict[str, str]:
        """Map construction definition args to actual point names."""
        mapping: dict[str, str] = {}

        # Calculate number of points needed
        if construction_def.declare[0] == 's_angle':
            n_needed = len(construction_def.args) - 1
            args_to_map = construction_def.args[:-1]
        else:
            n_needed = len(construction_def.args)
            args_to_map = construction_def.args

        candidate_points = defined_points
        points = random.sample(candidate_points, n_needed)
        mapping.update(dict(zip(args_to_map, points)))

        # Handle special angle case
        if construction_def.declare[0] == 's_angle':
            mapping[construction_def.args[-1]] = f'{random.choice(range(15, 180, 15))}o'

        return mapping

    def _format_construction_text(self, construction_def, mapping: dict) -> str:
        """Format construction text from definition and mapping."""
        text = f"{construction_def.declare[0]} {' '.join([mapping[p] for p in construction_def.declare[1:]])}"
        return text


def main():
    """简单测试。"""
    import time
    from collections import Counter

    seed = 42
    length = 20
    print(f"seed: {seed}, length: {length}\n")

    # 1. ClauseDAG 测试
    print("=== ClauseDAG 测试 ===")
    dag = ClauseDAG()
    dag.add_clause(Clause(('a@0_0', 'b@1_0', 'c@0.5_1'), (('triangle', 'a', 'b', 'c'),)))
    dag.add_clause(Clause(('d@0.5_0',), (('midpoint', 'd', 'a', 'b'),)))
    dag.add_clause(Clause(('e@0.25_0.5',), (('midpoint', 'e', 'a', 'c'),)))
    dag.add_clause(Clause(('f@0.375_0.25',), (('midpoint', 'f', 'd', 'e'),)))
    print(f"节点: {len(dag.nodes)}, 深度: {dag.get_max_depth()}")
    print(f"问题: {dag.to_problem(rename=True)}\n")

    # 2. 单个问题
    print("=== 单个问题 ===")
    sampler = ProblemSampler(seed=seed)
    result = sampler.generate(length=length, add_auxiliary=True, prune=True, with_coords=False)
    print(result)
    print(f"节点: {len(sampler.dag.nodes)}, 深度: {sampler.dag.get_max_depth()}\n")

    # 3. 批量生成
    print("=== 批量生成 (50题) ===")
    n_samples = 50
    depths = []
    point_counts = []
    start = time.time()

    for i in range(n_samples):
        s = ProblemSampler(seed=seed + i)
        s.generate(length=length, add_auxiliary=True, prune=True, with_coords=False)
        if s.dag.nodes:
            depths.append(s.dag.get_max_depth())
            point_counts.append(len(s.dag.get_all_points()))

    elapsed = time.time() - start
    print(f"耗时: {elapsed:.2f}s, 速度: {n_samples/elapsed:.1f}题/秒\n")

    # 深度分布 (排序 + barchart)
    print("深度分布:")
    depth_counts = Counter(depths)
    max_count = max(depth_counts.values())
    for d in sorted(depth_counts.keys()):
        count = depth_counts[d]
        bar_len = int(count / max_count * 40)
        bar = "█" * bar_len
        print(f"  {d}: {count:3d} {bar}")

    # 点数量分布
    print("\n点数量分布:")
    point_dist = Counter(point_counts)
    max_count = max(point_dist.values())
    for p in sorted(point_dist.keys()):
        count = point_dist[p]
        bar_len = int(count / max_count * 40)
        bar = "█" * bar_len
        print(f"  {p:2d}: {count:3d} {bar}")


if __name__ == "__main__":
    main()
