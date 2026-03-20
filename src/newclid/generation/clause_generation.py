from collections import defaultdict, OrderedDict
import re
from itertools import combinations
import numpy as np
import math
from collections import defaultdict
import random
import string
import numpy
import time
import logging
from typing import Union
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import translate_sentence
from newclid.statement import Statement
from newclid.configs import default_defs_path
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.predicates import NAME_TO_PREDICATE
from newclid.proof import ConstructionError
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.numerical.sketch import sketch
from newclid.numerical.geometries import (
    ObjNum,
    PointNum,
    reduce,
)
from newclid.numerical.distances import (
    PointTooCloseError,
    PointTooFarError,
    check_too_far_numerical,
    check_too_close_numerical,
)

MAX_TRY = 10

BASIC = [
    'segment',
    'triangle',
    'triangle12',
    'r_triangle',
    'iso_triangle',
    # 'iso_triangle0',
    'ieq_triangle',
    'risos',
    'quadrangle',
    'rectangle',
    'isquare',
    'trapezoid',
    'r_trapezoid',
    'iso_trapezoid',
    'eq_quadrangle',
    'eqdia_quadrangle',
    'pentagon',
]

BASIC_FREE = [
    'free',
]

INTERSECT = [
    'angle_bisector',  # => bisect => LineNum
    'angle_mirror',  # => amirror => LineNum
    'eqdistance',  # => circle => CircleNum
    'on_line',  # => line => LineNum
    'on_aline',  # => aline => LineNum
    # 'on_aline0', # => aline => LineNum
    'on_bline',  # => bline => LineNum
    'on_pline',  # => pline => LineNum
    # 'on_pline0', # => pline => LineNum
    'on_tline',  # => tline => LineNum
    'on_dia',  # => dia => CircleNum
    'on_circle',  # => circle => CircleNum
    'eqangle3',  # => eqangle3 => CircleNum
    'on_circum',  # => cyclic =>  CircleNum,
    'eqratio',  # => eqratio => CircleNum
    'eqratio6',  # => eqratio6 => LineNum / CircleNum
    'lc_tangent',  # => tline => LineNum  # should be here
    # TODO: double check. do we need this?
    # 'rconst', # => rconst => CircleNum
    # 'rconst2', # => rconst2 => LineNum / CircleNum
    # 'aconst', # => aconst => LineNum !一般在goal中，可以不放
    's_angle',  # => s_angle => LineNum
    # 'lconst', # => lconst => CircleNum
]

OTHER = [
    'circle',
    # 'circumcenter',
    'eq_triangle',
    'eqangle2',
    'foot',
    'incenter',
    'incenter2',
    'excenter',
    'excenter2',
    'centroid',
    'ninepoints',
    'intersection_cc',
    'intersection_lc',
    'intersection_ll',
    'intersection_lp',
    'intersection_lt',
    'intersection_pp',
    'intersection_tt',
    'midpoint',
    'mirror',
    # 'nsquare',
    'orthocenter',
    'parallelogram',
    # 'psquare',
    'reflect',
    # 'shift',
    'square',
    # '2l1c',
    # 'e5128',
    # '3peq',
    'trisect',
    'trisegment',
    'cc_tangent',
    'tangent',
    # 'iso_triangle_vertex',
    # 'iso_triangle_vertex_angle',
]


class PointGenerator:
    def __init__(self, max_points=260):
        """Point generator, creates unique point names"""
        self.max_points = max_points
        self.defined_points = []

    def get_point_name(self, va_idx):
        """Generate a point name using letters and numbers"""
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        # a, b, ..., z, a0, b0, ...
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    def prefetch_points(self, n):
        res = []
        for i in range(n):
            if len(self.defined_points) >= self.max_points:
                raise ValueError("All point names exhausted.")
            point_name = self.get_point_name(len(self.defined_points) + i)
            res.append(point_name)
        return res

    def define_points(self, points):
        for p in points:
            if len(self.defined_points) >= self.max_points:
                raise ValueError("All point names exhausted.")
            self.defined_points.append(p)


class CompoundClauseGen:
    # Configuration: Auxiliary point generation rules
    TRIANGLE_TYPES = ['triangle', 'triangle12',
                      'r_triangle', 'iso_triangle', 'ieq_triangle']

    AUXILIARY_POINT_RULES = {
        'midpoint': [
            ('midpoint', ['a', 'b']),
            ('midpoint', ['b', 'c']),
            ('midpoint', ['a', 'c']),
        ],
        'orthocenter': [
            ('orthocenter', ['a', 'b', 'c']),
            ('foot', ['a', 'b', 'c']),
            ('foot', ['b', 'a', 'c']),
            ('foot', ['c', 'a', 'b']),
        ],
        'circle': [('circle', ['a', 'b', 'c'])],
        'incenter2': [('incenter2', ['a', 'b', 'c'])],
        'excenter2': [('excenter2', ['a', 'b', 'c'])],
    }

    def __init__(self, seed=None, defs=None):
        """Initialize the compound clause generator"""
        self.defs = defs or DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_txt_file(default_defs_path())
        )
        self.rng = numpy.random.default_rng(seed)
        random.seed(seed)
        self.point_generator = None
        self.symbols_graph = None
        self.dep_graph = None
        self.point_level: dict[str, int] = None
        self.point_rely: dict[str, set[str]] = None

    def _is_first_clause_triangle(self, first_clause: str) -> bool:
        """Check if the first clause is a triangle"""
        if not first_clause:
            return False
        construction_type = first_clause.split("=")[1].strip().split()[0]
        return construction_type in self.TRIANGLE_TYPES

    def _add_auxiliary_points_if_needed(self, new_clause: str, first_clause: str, res: list):
        """Add auxiliary points for triangle constructions based on keywords"""
        if not self._is_first_clause_triangle(first_clause):
            return

        # Extract construction keywords from the new clause
        keywords = re.findall(
            r'(?:=|,)\s*([A-Za-z_][A-Za-z0-9_]*)', new_clause)

        # Generate auxiliary points based on rules using configuration
        for keyword in keywords:
            if keyword in self.AUXILIARY_POINT_RULES:
                for construction_type, args in self.AUXILIARY_POINT_RULES[keyword]:
                    auxiliary_clause = self.get_auxiliary_construction_clause(
                        construction_type, args)
                    if auxiliary_clause:
                        res.append(auxiliary_clause)

    def _validate_construction_requirements(self, construction_def, mapping) -> bool:
        """Validate construction requirements (premises)"""
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
        """Validate construction basic properties"""
        try:
            for bs in construction_def.basics:
                for t in bs.sentences:
                    Statement.from_tokens(
                        translate_sentence(mapping, t), self.dep_graph)
            return True
        except Exception as e:
            logging.warning(f"Error processing construction basics: {e}")
            return False

    def _extract_numerics(self, construction_def, mapping) -> list:
        """Extract numerical constraints from construction definition"""
        numerics = []
        for n in construction_def.numerics:
            numerics.append(
                tuple(mapping[a] if a in mapping else a for a in n))
        return numerics
    
    def _extract_construction_points(self, construction_def, mapping) -> set[Point]:
        """Extract construction points from construction definition"""
        construction_points = set()
        for arg in construction_def.args:
            if mapping[arg] in self.symbols_graph.name2node:
                construction_points.add(self.symbols_graph.name2node[mapping[arg]])
        return construction_points

    def _format_points_with_coords(self, point_names: list[str]) -> list[str]:
        """Format multiple point names with coordinates"""
        points = self.symbols_graph.names2points(point_names)
        return [f'{p.name}@{p.num.x}_{p.num.y}' for p in points]

    def _calculate_max_level(self, construction_text: str) -> int:
        """Calculate maximum level from construction dependencies"""
        depend_points = construction_text.split()[1:]
        levels = [self.point_level.get(p, -1) for p in depend_points]
        return max([-1] + levels)

    def _extract_rely_points(self, construction_text: str) -> set:
        """Extract dependency points from construction text"""
        depend_points = construction_text.split()[1:]
        return set(p for p in depend_points if p in self.point_rely)

    def generate(self, length=0, add_auxiliary=True, prune=True, remove_coords=False):
        """
        Generate geometric clauses.

        Args:
            length: Number of clause sets to generate
            add_auxiliary: Whether to add auxiliary points (e.g., midpoint, orthocenter) for triangles
            prune: Whether to prune clauses to preserve only the deepest clause chain
            remove_coords: Whether to remove coordinate information from the final output

        Returns:
            A string of generated clauses separated by semicolons
        """
        self.point_generator = PointGenerator()
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.symbols_graph = self.dep_graph.symbols_graph
        self.point_level = {}
        self.point_rely = {}

        res = []
        for clause_set in range(length):
            if clause_set == length - 1:
                pass
            # step 1: add clause with basic
            if len(res) == 0:
                new_clauses = self._get_clauses(
                    construction_candidates=BASIC,
                    n_constructions=1,
                    n_clauses=1,
                )
            # step 2: add clause with basic (free)
            # elif clause_set < max_basic_clause:
            #     new_clauses = self._get_clauses(
            #         construction_candidates=BASIC_FREE,
            #         n_constructions=1,
            #         n_clauses=1,
            #     )
            # step 3: add cluase with single constructions or two constructions
            else:
                if random.random() < 0.5:
                    new_clauses = self._get_clauses(
                        construction_candidates=INTERSECT,
                        n_constructions=2,
                        n_clauses=2,
                        n_points=1,
                    )
                else:
                    new_clauses = self._get_clauses(
                        construction_candidates=OTHER+INTERSECT+BASIC_FREE,
                        n_constructions=1,
                        n_clauses=1,
                    )
            res.extend(new_clauses)
            # Add auxiliary points if needed
            if new_clauses and add_auxiliary:
                self._add_auxiliary_points_if_needed(
                    new_clauses[0], res[0], res)

        # Prune clauses if requested
        if prune:
            res = self.prune_clauses(res)

        # Join clauses
        output = "; ".join(res)

        # Remove coordinate information if requested
        if remove_coords:
            output = re.sub(r'([a-z][0-9]*)@[^\s;]+', r'\1', output)

        return output

    def _get_clauses(
        self,
        construction_candidates: list[str],
        n_constructions: int,
        n_clauses: int,
        n_points: int = None,
    ) -> list[str]:
        """
        Generate clauses using specified construction candidates.

        Args:
            construction_candidates: List of candidate construction types
            n_constructions: Number of constructions to use per clause
            n_clauses: Number of clauses to generate (with same constructions)
            n_points: Number of new points to generate (optional). If None, determined by first construction.

        Returns:
            A list of generated clause strings
        """
        n_points_backup = n_points
        for _ in range(MAX_TRY):
            try:
                # Select constructions, map arguments, and extract numerics
                # If n_points is None, it will be set by the first construction
                (
                    selected_constructions,
                    args_mappings,
                    numeric_list,
                    construction_points,
                    n_points
                ) = self._get_constructions(
                    construction_candidates,
                    n_constructions,
                    n_points_backup,
                )
                # If unable to select enough constructions, retry
                if len(selected_constructions) != n_constructions:
                    continue

                # Determine max level and rely points from argument mappings
                # (same for all clauses with the same constructions)
                max_level: int = -1
                rely_points: set[str] = set()
                for mapping in args_mappings:
                    for arg in mapping.values():
                        max_level = max(
                            max_level, self.point_level.get(arg, -1))
                        if arg in self.point_generator.defined_points:
                            rely_points.add(arg)

                try:
                    # Apply constructions to generate clauses,
                    # update point levels and dependencies
                    clause_strs = self._apply_constructions(
                        selected_constructions,
                        args_mappings,
                        numeric_list,
                        construction_points,
                        n_clauses,
                        n_points,
                        max_level,
                        rely_points,
                    )
                except Exception as e:
                    # If clause application fails, retry
                    # May fail due to duplicate points, numerical issues, etc.
                    logging.debug(f"Clause application failed: {e}")
                    continue

                return clause_strs

            except Exception as e:
                logging.debug(f"Clause generation attempt failed: {e}")
                continue
        return []

    def _get_constructions(
        self,
        construction_candidates: list[str],
        n_constructions: int,
        n_points: int,
    ) -> tuple[list[str], list[dict[str, str]], list[tuple], int]:
        """
        Select constructions and map their arguments.

        Args:
            construction_candidates: List of candidate construction types
            n_constructions: Number of constructions to select
            n_points: Number of new points to generate (optional). If None, determined by first construction.

        Returns:
            A tuple of (selected_constructions, args_mappings, numeric_list, n_points)
            selected_constructions: List of selected construction types
            args_mappings: List of argument mappings for each construction
            numeric_list: List of numerical constraints extracted
            n_points: Number of new points to generate
        """
        selected_constructions: list[str] = []
        args_mappings: list[dict[str, str]] = []
        numeric_list: list[tuple] = []
        construction_points: set[Point] = set()
        for _ in range(n_constructions):
            random_construction_candidates = construction_candidates.copy()
            self.rng.shuffle(random_construction_candidates)
            for construction in random_construction_candidates:
                construction_def = self.defs[construction]

                if n_points is None:
                    # n_points not specified,
                    # accept the point count of the first construction
                    n_points = len(construction_def.points)
                elif len(construction_def.points) != n_points:
                    continue

                if len(construction_def.args) > len(self.point_generator.defined_points):
                    continue

                args_mapping = self._map_args(
                    construction_def,
                    self.point_generator.defined_points,
                )
                if not self._validate_construction_requirements(construction_def, args_mapping):
                    continue
                numerics = self._extract_numerics(construction_def, args_mapping)
                new_construction_points = self._extract_construction_points(
                    construction_def, args_mapping
                )

                selected_constructions.append(construction)
                args_mappings.append(args_mapping)
                numeric_list.extend(numerics)
                construction_points.update(new_construction_points)

                # Successfully selected a construction, break to select next
                break
        return selected_constructions, args_mappings, numeric_list, construction_points, n_points

    def _apply_constructions(
        self,
        selected_constructions: list[str],
        args_mappings: list[dict[str, str]],
        numeric_list: list[tuple],
        construction_points: set[Point],
        n_clauses: int,
        n_points: int,
        max_level: int,
        rely_points: set[str],
    ) -> list[str]:
        """Apply selected constructions to generate clauses."""
        clause_strs: list[str] = []
        # Generate n_clauses clauses with the same constructions
        for i in range(n_clauses):
            try:
                new_points = self.point_generator.prefetch_points(n_points)
                # Check numerics by drawing diagram
                self.draw_diagram(new_points, numeric_list, construction_points)
                self.point_generator.define_points(new_points)

                # Update point levels and dependencies
                for p in new_points:
                    self.point_level[p] = max_level + 1
                    self.point_rely[p] = rely_points

                construction_strs: list[str] = []
                for construction, mapping in zip(selected_constructions, args_mappings):
                    mapping.update(
                        dict(zip(self.defs[construction].points, new_points)))
                    construction_strs.append(
                        self.construction_text(
                            self.defs[construction], mapping)
                    )

                    self._validate_construction_basics(
                        self.defs[construction], mapping
                    )

                new_point_strs = self._format_points_with_coords(new_points)
                clause_str = ' '.join(new_point_strs) + \
                    " = " + ', '.join(construction_strs)
                clause_strs.append(clause_str)
            except Exception as e:
                if i == 0:
                    # for the first clause, we must succeed
                    raise e
                else:
                    # for subsequent clauses, we can skip on failure and return what we have
                    logging.debug(
                        f"Multiple clause generation attempt failed: {e}")
                    break
        return clause_strs

    def get_auxiliary_construction_clause(self, construction, rpoints):
        """
        Generate auxiliary construction clause with strict point order.

        Args:
            construction: A single construction type string (e.g., 'midpoint')
            rpoints: List of point names to use as construction arguments in exact order

        Returns:
            A string representing the auxiliary construction clause, or None if generation fails
        """
        try:
            construction_def = self.defs[construction]
            args_mapping = dict(zip(construction_def.args, rpoints))
            if not self._validate_construction_requirements(construction_def, args_mapping):
                raise Exception("Requirement validation failed.")
            numerics = self._extract_numerics(construction_def, args_mapping)
            construction_points = self._extract_construction_points(
                construction_def, args_mapping
            )

            clause_str = self._apply_constructions(
                selected_constructions=[construction],
                args_mappings=[args_mapping],
                numeric_list=numerics,
                construction_points_sets=construction_points,
                n_clauses=1,
                n_points=len(construction_def.points),
                max_level=max([self.point_level[p] for p in rpoints]),
                rely_points=set(rpoints),
            )

            return clause_str[0]

        except Exception as e:
            logging.debug(f"Auxiliary construction generation failed: {e}")
            return None

    def draw_diagram(self, new_points, numerics, construction_points):
        def draw_fn() -> tuple[PointNum, ...]:
            to_be_intersected: list[ObjNum] = []
            for n in numerics:
                args: list[Union[PointNum, str]] = []
                for t in n[1:]:
                    if str.isalpha(t[0]):  # a1 => a
                        args.append(
                            self.symbols_graph.names2points([t])[0].num)
                    else:
                        args.append(t)
                to_be_intersected += sketch(n[0], tuple(args), self.rng)

            return reduce(
                to_be_intersected,
                [p.num for p in _existing_points],
                [p.num for p in construction_points],
                rng=self.rng,
            )

        # some points are created in previous draw, but not pass the check. we should replace this points
        _existing_points = list(self.symbols_graph.nodes_of_type(Point))
        _existing_points = [p for p in _existing_points if hasattr(p, "num")]
        _new_points = self.symbols_graph.names2points(new_points)
        _new_numerical_point = draw_fn()

        # check draw result
        if len(_new_numerical_point) != len(_new_points):
            raise Exception("why no error ??? TO FIX!!!")

        # check point distance
        _existing_numerical_points = [p.num for p in _existing_points]
        if check_too_close_numerical(_new_numerical_point, _existing_numerical_points, round=-1.0):
            raise PointTooCloseError()
        if check_too_far_numerical(_new_numerical_point, _existing_numerical_points):
            raise PointTooFarError()

        # set point position
        for p, num in zip(_new_points, _new_numerical_point):
            p.num = num

    def _map_args(
        self,
        construction_def: DefinitionJGEX,
        defined_points: list[str],
    ) -> dict[str, str]:
        """Map construction definition args to actual point names."""
        mapping: dict[str, str] = {}

        # 计算本次构造需要的点数量
        if construction_def.declare[0] == 's_angle':
            n_needed = len(construction_def.args) - 1
            args_to_map = construction_def.args[:-1]
        else:
            n_needed = len(construction_def.args)
            args_to_map = construction_def.args

        candidate_points = defined_points
        points = random.sample(candidate_points, n_needed)
        mapping.update(dict(zip(args_to_map, points)))

        # 处理特殊的角度情况
        if construction_def.declare[0] == 's_angle':
            mapping[construction_def.args[-1]
                    ] = f'{random.choice(range(15, 180, 15))}o'

        return mapping

    def construction_text(self, construction_def, mapping):
        text = f"{construction_def.declare[0]} {' '.join([mapping[p] for p in construction_def.declare[1:]])}"
        return text

    def prune_clauses(self, clauses: list[str]) -> list[str]:
        """Prune clauses to preserve only the deepest clause chain"""
        max_level = max(self.point_level.values())
        useful_points = [random.choice(
            [p for p, l in self.point_level.items() if l == max_level])]
        for p in useful_points:
            for q in self.point_rely[p]:
                if q not in useful_points:
                    useful_points.append(q)
        pruned_clauses = []
        for clause in clauses:
            clause_points = clause.split('=')[0].strip().split()
            if any(p.split('@')[0] in useful_points for p in clause_points):
                pruned_clauses.append(clause)
        return pruned_clauses


def process_geometric_string(input_str):
    # 步骤1: 移除所有点定义中的坐标部分
    cleaned_str = re.sub(r'([a-z][0-9]*)@[^\s;]+', r'\1', input_str)
    # 步骤2: 计算每个点的深度
    depth_map = defaultdict(int)
    statements = [stmt.strip()
                  for stmt in cleaned_str.split(';') if stmt.strip()]
    for stmt in statements:
        if not stmt or '=' not in stmt:
            continue
        lhs, rhs = [part.strip() for part in stmt.split('=', 1)]
        current_points = [p.strip() for p in lhs.split() if p.strip()]
        # 提取所有依赖点（右侧出现的所有小写字母）
        dependencies = set()
        conditions = [cond.strip() for cond in rhs.split(',') if cond.strip()]
        for cond in conditions:
            tokens = re.findall(r'\b[a-z][0-9]*\b', cond)
            for token in tokens:
                if token not in current_points:
                    dependencies.add(token)
        # 计算当前点的深度
        for point in current_points:
            if rhs.startswith('free') or not dependencies:
                depth_map[point] = 1
            else:
                max_dep_depth = 0
                for dep in dependencies:
                    if dep in depth_map and depth_map[dep] > max_dep_depth:
                        max_dep_depth = depth_map[dep]
                depth_map[point] = max_dep_depth + 1
    # 按字母顺序排序深度结果
    sorted_depths = dict(sorted(depth_map.items()))
    # 计算最大深度
    max_depth = max(sorted_depths.values()) if sorted_depths else 0
    return cleaned_str, sorted_depths, max_depth


# ----------------------------- 配置与常量 -----------------------------
TOLERANCE = 1e-8          # 浮点比较容差
ROUND_DECIMALS = 9       # 坐标保留小数位数（避免浮点误差积累）


def find_potential_points(text: str, min_duplicated: int = 3):
    """
    输入：包含点定义的几何描述字符串（格式如 a@x_y b@x_y ...）
    输出：repeated_points 列表，其中每个元素是一个至少出现3次的构造点（不在原始点中），
          包含坐标和该点在不同构造方式下的所有出现信息。
    不修改原实现的任何逻辑，仅去除所有print输出并封装成函数。
    """

    # ----------------------------- 提取原始点 -----------------------------
    pattern = r'([a-zA-Z][a-zA0-9]*)@([-+]?\d*\.?\d+)_([-+]?\d*\.?\d+)'
    matches = re.findall(pattern, text)

    original_points = OrderedDict()
    for name, x_str, y_str in matches:
        original_points[name] = (float(x_str), float(y_str))

    point_names = list(original_points.keys())
    coords = np.array([original_points[name] for name in point_names])

    # ----------------------------- 工具函数 -----------------------------
    def round_coord(coord):
        return (round(coord[0], ROUND_DECIMALS), round(coord[1], ROUND_DECIMALS))

    def normalize_direction(dx, dy):
        norm = np.sqrt(dx**2 + dy**2)
        return (0.0, 0.0) if norm < TOLERANCE else (dx / norm, dy / norm)

    def is_point_too_close(
        new_coords: list[tuple[float, float]],
        existing_coords: list[tuple[float, float]],
        tol: float = 0.05,
        round_eps: float = 1e-10
    ) -> bool:
        """
        判断新点是否跟已有点「靠得太近」
        - 如果已有点少于2个 → 不算太近
        - 计算已有点的平均点间距（粗略）
        - 如果新点到某个已有点的距离 在 (round_eps ~ tol × 平均间距) 之间 → 认为太近
        """
        if len(existing_coords) < 2:
            return False

        # 计算所有点对的平均距离（近似平均点间距）
        total_dist = 0.0
        count = 0
        n = len(existing_coords)
        for i in range(n):
            for j in range(i + 1, n):
                x1, y1 = existing_coords[i]
                x2, y2 = existing_coords[j]
                dist = ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5
                total_dist += dist
                count += 1
        avg_dist = total_dist / count

        # 检查每个新点
        for nx, ny in new_coords:
            for px, py in existing_coords:
                dx = nx - px
                dy = ny - py
                dist = (dx*dx + dy*dy) ** 0.5
                if round_eps < dist < tol * avg_dist:
                    return True
        return False

    def is_point_too_far(
        new_coords: list[tuple[float, float]],
        existing_coords: list[tuple[float, float]],
        factor: float = 5.0
    ) -> bool:
        """
        原始风格的“太远”判断：
        只要新点与「任何一个」已有旧点的距离 > factor × 尺度，就认为太远。
        （注意：这和“离最近点太远”或“离所有点太远”是不同的语义）
        """
        if len(existing_coords) < 2:
            return False

        # 计算质心（平均位置）
        n = len(existing_coords)
        sum_x = sum(y for x, y in existing_coords)
        sum_y = sum(y for x, y in existing_coords)
        avg_x = sum_x / n
        avg_y = sum_y / n

        # 计算到质心的最大距离（作为点群尺度）
        maxdist = 0.0
        for px, py in existing_coords:
            dx = px - avg_x
            dy = py - avg_y
            dist = (dx*dx + dy*dy) ** 0.5
            if dist > maxdist:
                maxdist = dist

        for nx, ny in new_coords:
            for px, py in existing_coords:
                dx = nx - px
                dy = ny - py
                dist = (dx*dx + dy*dy) ** 0.5
                if dist > factor * maxdist:
                    return True
        return False

    # ----------------------------- 生成中点 -----------------------------
    midpoints = []
    midpoint_counter = 1
    for p1, p2 in combinations(point_names, 2):
        x1, y1 = original_points[p1]
        x2, y2 = original_points[p2]
        mid_coord = round_coord(((x1 + x2) / 2, (y1 + y2) / 2))
        new_name = f"m{midpoint_counter}"
        midpoints.append((new_name, mid_coord, "midpoint", [p1, p2]))
        midpoint_counter += 1

    # ----------------------------- 点关于点的对称（reflection over point） -----------------------------
    reflections_over_point = []
    refl_point_counter = 1
    for center_name in point_names:  # 中心点（对称中心）
        for pt_name in point_names:  # 被对称的点
            if pt_name == center_name:
                continue
            center_coord = original_points[center_name]
            pt_coord = original_points[pt_name]
            sym_coord = round_coord((
                2 * center_coord[0] - pt_coord[0],
                2 * center_coord[1] - pt_coord[1]
            ))
            new_name = f"sympt{refl_point_counter}"
            reflections_over_point.append(
                (new_name, sym_coord, "symmetric_over_point", [center_name, pt_name]))
            refl_point_counter += 1

    # ----------------------------- 检测共线组（直线） -----------------------------
    line_to_points = defaultdict(set)

    for i, j in combinations(range(len(point_names)), 2):
        if i >= j:
            continue
        p1, p2 = coords[i], coords[j]
        dir_norm = normalize_direction(p2[0] - p1[0], p2[1] - p1[1])
        if dir_norm == (0.0, 0.0):
            continue
        key = (p1[0], p1[1], dir_norm[0], dir_norm[1])
        line_to_points[key].update([point_names[i], point_names[j]])

    final_lines = []
    for key, pts_set in line_to_points.items():
        current_pts = sorted(list(pts_set))
        current_indices = [point_names.index(p) for p in current_pts]
        while True:
            added = False
            max_dist = -1
            base1_idx, base2_idx = current_indices[0], current_indices[1]

            for ii in range(len(current_indices)):
                for jj in range(ii + 1, len(current_indices)):
                    a = current_indices[ii]
                    b = current_indices[jj]
                    dist_sq = (coords[a][0] - coords[b][0])**2 + \
                        (coords[a][1] - coords[b][1])**2
                    if dist_sq > max_dist:
                        max_dist = dist_sq
                        base1_idx, base2_idx = a, b

            direction = coords[base2_idx] - coords[base1_idx]
            dir_norm = np.linalg.norm(direction)

            for k in range(len(point_names)):
                if point_names[k] in pts_set:
                    continue
                pt = coords[k]
                vec = pt - coords[base1_idx]
                # 点到直线的距离（向量叉积 / 方向向量长度）
                dist = abs(np.cross(direction, vec)) / dir_norm

                if dist < TOLERANCE:
                    pts_set.add(point_names[k])
                    current_pts.append(point_names[k])
                    current_indices.append(k)
                    added = True
            if not added:
                break
        if len(pts_set) >= 2:  # 至少两条点才算有效线
            final_lines.append(sorted(list(pts_set)))

    unique_lines = sorted(
        {tuple(sorted(line)) for line in final_lines},
        key=lambda x: (-len(x), x)
    )

    # ----------------------------- 线交点 -----------------------------
    def line_intersection(line1_pts, line2_pts):
        if set(line1_pts) & set(line2_pts):
            return None

        A = coords[point_names.index(line1_pts[0])]
        B = coords[point_names.index(line1_pts[1])]
        C = coords[point_names.index(line2_pts[0])]
        D = coords[point_names.index(line2_pts[1])]

        AB = B - A
        CD = D - C
        denom = np.cross(AB, CD)
        if abs(denom) < TOLERANCE:
            return None
        t = np.cross(C - A, CD) / denom
        return A + t * AB

    intersections = []
    inter_counter = 1
    for line1, line2 in combinations(unique_lines, 2):
        inter = line_intersection(line1, line2)
        if inter is not None:
            new_name = f"inter{inter_counter}"
            intersections.append((new_name, round_coord(inter), "intersection", [
                                 sorted(line1), sorted(line2)]))
            inter_counter += 1

    # ----------------------------- 垂足和关于线的对称点 -----------------------------
    def point_to_line_foot_and_reflect(pt_coord, line_pts):
        A = coords[point_names.index(line_pts[0])]
        B = coords[point_names.index(line_pts[1])]
        AB = B - A
        AP = pt_coord - A
        proj = np.dot(AP, AB) / np.dot(AB, AB)
        foot_coord = A + proj * AB
        sym_coord = (2 * foot_coord[0] - pt_coord[0],
                     2 * foot_coord[1] - pt_coord[1])
        return foot_coord, sym_coord

    feet = []
    reflections_over_line = []
    counter = 1

    for line in unique_lines:
        line_sorted = sorted(line)
        for pt_name in point_names:
            if pt_name in line_sorted:
                continue
            pt_coord = original_points[pt_name]
            foot_coord, sym_coord = point_to_line_foot_and_reflect(
                pt_coord, line_sorted)
            new_name = f"foot{counter}"
            feet.append((new_name, round_coord(foot_coord),
                        "foot", [pt_name, line_sorted]))
            new_name = f"symline{counter}"
            reflections_over_line.append(
                (new_name, round_coord(sym_coord), "symmetric_over_line", [pt_name, line_sorted]))
            counter += 1

    new_feet = []
    for foot in feet:
        name, coord, typ, deps = foot
        line_points = deps[1]
        remaining = list(line_points)
        for p in line_points:
            p_coord = original_points[p]
            if (abs(coord[0] - p_coord[0]) < TOLERANCE and
                    abs(coord[1] - p_coord[1]) < TOLERANCE):
                remaining.remove(p)
                break
        if len(remaining) >= 2:
            new_deps = [deps[0], remaining]
            new_feet.append((name, coord, typ, new_deps))
    feet = new_feet

    # ----------------------------- 共圆检测 -----------------------------

    def get_circle_from_three(p1, p2, p3):
        i1, i2, i3 = (point_names.index(p) for p in (p1, p2, p3))
        A, B, C = coords[i1], coords[i2], coords[i3]

        ba, ca = B - A, C - A
        if abs(np.cross(ba, ca)) < TOLERANCE:
            return None

        D = 2 * (A[0]*(B[1]-C[1]) + B[0]*(C[1]-A[1]) + C[0]*(A[1]-B[1]))
        if abs(D) < TOLERANCE:
            return None

        ux = ((A[0]**2 + A[1]**2)*(B[1]-C[1]) + (B[0]**2 + B[1]**2)
              * (C[1]-A[1]) + (C[0]**2 + C[1]**2)*(A[1]-B[1])) / D
        uy = ((A[0]**2 + A[1]**2)*(C[0]-B[0]) + (B[0]**2 + B[1]**2)
              * (A[0]-C[0]) + (C[0]**2 + C[1]**2)*(B[0]-A[0])) / D
        center = (ux, uy)
        radius = np.linalg.norm(np.array(center) - A)
        return center, radius

    def point_on_circle(pt_name, center, radius):
        dist = np.linalg.norm(
            np.array(center) - original_points[pt_name])
        return abs(dist - radius) < 2e-8

    raw_circles = defaultdict(set)
    for comb in combinations(point_names, 3):
        cir = get_circle_from_three(*comb)
        if cir:
            raw_circles[cir].update(comb)

    circles = []
    for (center, radius), pts in raw_circles.items():
        all_pts = set(pts)
        for pt in point_names:
            if pt not in all_pts and point_on_circle(pt, center, radius):
                all_pts.add(pt)
        circles.append({"center": center, "radius": radius,
                       "points": sorted(all_pts)})

    circles_by_points = defaultdict(list)
    for cir in circles:
        points_key = frozenset(cir["points"])
        circles_by_points[points_key].append(cir)

    dedup_circles = []
    for points_key, group in circles_by_points.items():
        if len(group) == 1:
            dedup_circles.append(group[0])
        else:
            group.sort(key=lambda x: x["radius"])
            representative = group[len(group) // 2]
            dedup_circles.append({
                "center": representative["center"],
                "radius": representative["radius"],
                "points": sorted(points_key)
            })

    dedup_circles.sort(key=lambda x: (-len(x["points"]), x["radius"]))
    circles = dedup_circles

    # ----------------------------- 生成圆心点 -----------------------------
    circle_centers = []
    center_counter = 1

    for cir in circles:
        center_coord = cir["center"]
        new_name = f"center{center_counter}"
        circle_centers.append(
            (new_name, round_coord(center_coord), "circle_center", cir["points"]))
        center_counter += 1

    # ----------------------------- 线与圆交点 -----------------------------
    def line_circle_intersections(line_pts, circle):
        center = circle["center"]
        radius = circle["radius"]
        A = coords[point_names.index(line_pts[0])]
        d_vec = coords[point_names.index(line_pts[1])] - A
        f = A - np.array(center)
        a = np.dot(d_vec, d_vec)
        b = 2 * np.dot(f, d_vec)
        c = np.dot(f, f) - radius**2
        disc = b**2 - 4*a*c
        if disc < -TOLERANCE:
            return []
        disc = max(0, disc)
        sqrt_disc = np.sqrt(disc)
        candidates = []
        for sign in [1, -1]:
            t = (-b + sign * sqrt_disc) / (2*a)
            inter = A + t * d_vec
            candidates.append(inter)

        known_points = set(circle["points"]) | set(line_pts)
        known_points = [round_coord(
            (original_points[p][0], original_points[p][1])) for p in known_points]

        inters = [pt for pt in candidates if round_coord(
            pt) not in known_points]
        unique = []
        for pt in inters:
            if not any(abs(pt[0]-u[0]) < TOLERANCE and abs(pt[1]-u[1]) < TOLERANCE for u in unique):
                unique.append(pt)
        return unique

    circle_line_inters = []
    counter = 1

    for cir in circles:
        for line in unique_lines:
            pts = line_circle_intersections(line, cir)
            for pt in pts:
                new_name = f"cirinter{counter}"
                circle_line_inters.append(
                    (new_name, round_coord(pt), "circle_line_inter", [line, cir["points"]]))
                counter += 1

    # ----------------------------- 圆与圆交点 -----------------------------
    def circle_circle_intersections(cir1, cir2):
        c1 = np.array(cir1["center"])
        c2 = np.array(cir2["center"])
        r1 = cir1["radius"]
        r2 = cir2["radius"]

        d_vec = c2 - c1
        d = np.linalg.norm(d_vec)

        if d < TOLERANCE:
            return []

        if d > r1 + r2 + TOLERANCE:
            return []
        if d + min(r1, r2) < max(r1, r2) - TOLERANCE:
            return []

        a = (r1**2 - r2**2 + d**2) / (2 * d)
        h_squared = r1**2 - a**2

        h = np.sqrt(max(0.0, h_squared))

        P = c1 + a * (d_vec / d)

        if h < TOLERANCE:
            candidates = [tuple(P)]
        else:
            perp_vec = np.array([-d_vec[1], d_vec[0]])
            perp_norm = np.linalg.norm(perp_vec)
            if perp_norm < 1e-9:  # 几乎不可能，但防止除0
                return []
            perp_unit = perp_vec / perp_norm

            pt1 = P + h * perp_unit
            pt2 = P - h * perp_unit

            candidates = [
                tuple(pt1),
                tuple(pt2)
            ]

        known_points = set(cir1["points"]) & set(cir2["points"])
        known_points = [round_coord((
            original_points[p][0], original_points[p][1])) for p in known_points]

        result = []
        for pt in candidates:
            if round_coord(pt) not in known_points:
                result.append(pt)

        unique = []
        for pt in result:
            if not any(np.hypot(pt[0]-u[0], pt[1]-u[1]) < TOLERANCE*2 for u in unique):
                unique.append(pt)

        return unique

    abcd = {'a', 'b', 'c', 'd'}
    circles = [c for c in circles if len(
        c["points"]) >= 4 or all(p in abcd for p in c["points"])]

    # 两两组合圆（避免自交
    circle_circle_inters = []
    counter = 1

    for i, cir1 in enumerate(circles):
        for cir2 in circles[i+1:]:
            pts = circle_circle_intersections(cir1, cir2)
            for pt in pts:
                new_name = f"ccinter{counter}"
                circle_circle_inters.append(
                    (new_name, round_coord(pt), "circle_circle_inter", [cir1["points"], cir2["points"]]))
                counter += 1

    # ----------------------------- 汇总重复出现的构造点 -----------------------------
    all_generated = midpoints + intersections + feet + circle_line_inters + \
        circle_centers + reflections_over_point + \
        reflections_over_line + circle_circle_inters

    coord_to_appearances = defaultdict(list)
    for name, coord, typ, info in all_generated:
        coord_to_appearances[coord].append((name, typ, info))

    repeated_points = []
    existing_coords = list(original_points.values())
    for coord, apps in coord_to_appearances.items():
        if len(apps) >= min_duplicated:
            repeated_points.append((coord, apps))
    repeated_points.sort(key=lambda x: (-len(x[1]), random.random()))

    selected = []
    for coord, apps in repeated_points:
        # 检查单个点：[coord] 是 list of tuples
        if (not is_point_too_close([coord], existing_coords) and
                not is_point_too_far([coord], existing_coords)):
            selected.append((coord, apps))
            existing_coords.append(coord)

    return selected


def enhance_text_with_potential_points(original_text: str, generator: PointGenerator) -> str:
    MAX_TOTAL_POINTS = 25
    MAX_NEW_POINTS = 8

    repeated_points = find_potential_points(original_text, 3)
    if not repeated_points:
        return original_text

    # 当前已定义的点数
    current_count = len(generator.defined_points)
    # remaining_slots = max(0, MAX_TOTAL_POINTS - current_count)
    remaining_slots = MAX_NEW_POINTS

    if len(repeated_points) > remaining_slots:
        repeated_points = repeated_points[:remaining_slots]

    new_clauses = []
    wanted_new_points = len(repeated_points)

    try:
        new_point_names = generator.prefetch_points(wanted_new_points)
        generator.define_points(new_point_names)
    except ValueError:
        return original_text

    for (coord, appearances), new_name in zip(repeated_points, new_point_names):
        if not appearances:
            continue
        app = random.choice(appearances)
        clause = generate_clause_for_potential_point(coord, app, new_name)
        new_clauses.append(clause)

    if not new_clauses:
        return original_text

    additional_part = "; ".join(new_clauses)
    enhanced = original_text.rstrip()
    enhanced += '; ' + additional_part

    return enhanced


def generate_clause_for_potential_point(coord, appearance, new_name):
    """
    根据一种随机的构造方式，为一个 potential_point 生成对应的描述语句
    """
    x, y = coord
    coord_str = f"{x:.10f}_{y:.10f}".rstrip('0').rstrip('.')  # 去掉多余的0和小数点

    name, typ, info = appearance

    if typ == "midpoint":
        p1, p2 = info
        clause = f"midpoint {new_name} {p1} {p2}"

    elif typ == "intersection":
        line1, line2 = info
        pt1, pt2 = random.sample(line1, 2)
        pt3, pt4 = random.sample(line2, 2)
        clause = f"on_line {new_name} {pt1} {pt2}, on_line {new_name} {pt3} {pt4}"

    elif typ == "foot":
        pt, line = info
        a, b = random.sample(line, 2)
        clause = f"foot {new_name} {pt} {a} {b}"

    elif typ == "circle_center":
        circle = info
        a, b, c = random.sample(circle, 3)
        clause = f"circumcenter {new_name} {a} {b} {c}"

    elif typ == "circle_line_inter":
        line, circle = info
        circ_a, circ_b, circ_c = random.sample(circle, 3)
        line_d, line_e = random.sample(line, 2)
        clause = f"on_line {new_name} {line_d} {line_e}, on_circum {new_name} {circ_a} {circ_b} {circ_c}"

    elif typ == "circle_circle_inter":
        circle1, circle2 = info
        circ1_a, circ1_b, circ1_c = random.sample(circle1, 3)
        circ2_a, circ2_b, circ2_c = random.sample(circle2, 3)
        clause = (
            f"on_circum {new_name} {circ1_a} {circ1_b} {circ1_c}, "
            f"on_circum {new_name} {circ2_a} {circ2_b} {circ2_c}"
        )

    elif typ == "symmetric_over_point":
        center, original = info
        clause = f"mirror {new_name} {original} {center}"

    elif typ == "symmetric_over_line":
        pt, line = info
        a, b = random.sample(line, 2)
        clause = f"reflect {new_name} {pt} {a} {b}"

    else:
        clause = f"% unknown type {typ} for {new_name}"

    return f"{new_name}@{coord_str} = {clause}"


if __name__ == "__main__":
    cc_gen = CompoundClauseGen(42)
    # count=1000
    # sum = 0
    # for i in range(count):
    #     clause_text = cc_gen.generate(15)
    #     cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
    #     sum += len(sorted_depths)
    # print(sum/count)

    # sum = 0
    # for i in range(count):
    #     clause_text = cc_gen.generate(30)
    #     cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
    #     sum += len(sorted_depths)
    # print(sum/count)

    # import pdb; pdb.set_trace()
    # clause_text = cc_gen.generate(50, prune=False)
    # print(clause_text)
    # clause_text = cc_gen.generate(50)
    # print(clause_text)
    # clause_text = cc_gen.generate(50)
    # print(clause_text)
    # for i in range(20):
    #     s_time = time.time()
    #     cc_gen = CompoundClauseGen(i)
    #     clause_text = cc_gen.generate(50)
    #     print(f'{time.time() - s_time:.2f}s')
    for _ in range(200, 1000):
        cc_gen = CompoundClauseGen(_)
        clause_text = cc_gen.generate(50)
        cleaned_str, sorted_depths, max_depth = process_geometric_string(
            clause_text)
        print(
            f'seed: {_}, Max Depth: {max_depth}, Points: {len(sorted_depths)}')
        # print(f'Clauses: {clause_text}')
        print(f'Cleaned_str: {cleaned_str}\n')

    # cc_gen = CompoundClauseGen(998)
    # clause_text = cc_gen.generate(50, prune=False)
    # print(clause_text)
    # cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
    # print(f'Max Depth: {max_depth}, Points: {len(sorted_depths)}')
    # print(f'Cleaned_str: {cleaned_str}\n')
