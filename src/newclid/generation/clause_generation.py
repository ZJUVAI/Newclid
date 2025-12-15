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
    'angle_bisector', # => bisect => LineNum
    'angle_mirror', # => amirror => LineNum
    'eqdistance', # => circle => CircleNum     
    'on_line', # => line => LineNum
    'on_aline', # => aline => LineNum
    # 'on_aline0', # => aline => LineNum
    'on_bline', # => bline => LineNum
    'on_pline', # => pline => LineNum
    # 'on_pline0', # => pline => LineNum
    'on_tline', # => tline => LineNum
    'on_dia', # => dia => CircleNum
    'on_circle', # => circle => CircleNum
    'eqangle3', # => eqangle3 => CircleNum
    'on_circum', # => cyclic =>  CircleNum, 
    'eqratio', # => eqratio => CircleNum
    'eqratio6',  # => eqratio6 => LineNum / CircleNum
    'lc_tangent', # => tline => LineNum  # should be here
    # TODO: double check. do we need this?
    # 'rconst', # => rconst => CircleNum
    # 'rconst2', # => rconst2 => LineNum / CircleNum
    # 'aconst', # => aconst => LineNum !一般在goal中，可以不放
    's_angle', # => s_angle => LineNum 
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
        return f"{letter_part}{number_part - 1}" if number_part else letter_part  # a, b, ..., z, a0, b0, ...

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
    TRIANGLE_TYPES = ['triangle', 'triangle12', 'r_triangle', 'iso_triangle', 'ieq_triangle']
    
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
    
    def __init__(self, seed = None, defs=None):
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
        keywords = re.findall(r'(?:=|,)\s*([A-Za-z_][A-Za-z0-9_]*)', new_clause)
        
        # Generate auxiliary points based on rules using configuration
        for keyword in keywords:
            if keyword in self.AUXILIARY_POINT_RULES:
                for construction_type, args in self.AUXILIARY_POINT_RULES[keyword]:
                    auxiliary_clause = self.get_auxiliary_construction_clause(construction_type, args)
                    if auxiliary_clause:
                        res.append(auxiliary_clause)
    
    def _validate_construction_requirements(self, construction_def, mapping) -> bool:
        """Validate construction requirements (premises)"""
        try:
            for premise in construction_def.require.sentences:
                if len(premise) == 0:
                    continue
                statement = Statement.from_tokens(translate_sentence(mapping, premise), self.dep_graph)
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
                    Statement.from_tokens(translate_sentence(mapping, t), self.dep_graph)
            return True
        except Exception as e:
            logging.warning(f"Error processing construction basics: {e}")
            return False
    
    def _extract_numerics(self, construction_def, mapping) -> list:
        """Extract numerical constraints from construction definition"""
        numerics = []
        for n in construction_def.numerics:
            numerics.append(tuple(mapping[a] if a in mapping else a for a in n))
        return numerics
    
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

        max_basic_clause = int(0.15 * length)
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
                self._add_auxiliary_points_if_needed(new_clauses[0], res[0], res)
            
        
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
                selected_constructions, args_mappings, numeric_list, n_points = self._get_constructions(
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
                        max_level = max(max_level, self.point_level.get(arg, -1))
                        if arg in self.point_generator.defined_points:
                            rely_points.add(arg)
                
                try:
                    # Apply constructions to generate clauses,
                    # update point levels and dependencies
                    clause_strs = self._apply_constructions(
                        selected_constructions,
                        args_mappings,
                        numeric_list,
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

                selected_constructions.append(construction)
                args_mappings.append(args_mapping)
                numeric_list.extend(numerics)

                # Successfully selected a construction, break to select next
                break
        return selected_constructions, args_mappings, numeric_list, n_points
    
    def _apply_constructions(
        self,
        selected_constructions: list[str],
        args_mappings: list[dict[str, str]],
        numeric_list: list[tuple],
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
                self.draw_diagram(new_points, numeric_list)
                self.point_generator.define_points(new_points)

                # Update point levels and dependencies
                for p in new_points:
                    self.point_level[p] = max_level + 1
                    self.point_rely[p] = rely_points

                construction_strs: list[str] = []
                for construction, mapping in zip(selected_constructions, args_mappings):
                    mapping.update(dict(zip(self.defs[construction].points, new_points)))
                    construction_strs.append(
                        self.construction_text(self.defs[construction], mapping)
                    )

                    self._validate_construction_basics(
                        self.defs[construction], mapping
                    )

                new_point_strs = self._format_points_with_coords(new_points)
                clause_str = ' '.join(new_point_strs) + " = " + ', '.join(construction_strs)
                clause_strs.append(clause_str)
            except Exception as e:
                if i == 0:
                    # for the first clause, we must succeed
                    raise e
                else:
                    # for subsequent clauses, we can skip on failure and return what we have
                    logging.debug(f"Multiple clause generation attempt failed: {e}")
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
            
            clause_str = self._apply_constructions(
                selected_constructions=[construction],
                args_mappings=[args_mapping],
                numeric_list=numerics,
                n_clauses=1,
                n_points=len(construction_def.points),
                max_level=max([self.point_level[p] for p in rpoints]),
                rely_points=set(rpoints),
            )

            return clause_str[0]
            
        except Exception as e:
            logging.debug(f"Auxiliary construction generation failed: {e}")
            return None
    
    def draw_diagram(self, new_points, numerics,):
        def draw_fn() -> tuple[PointNum, ...]:
            to_be_intersected: list[ObjNum] = []
            for n in numerics:
                args: list[Union[PointNum, str]] = []
                for t in n[1:]:
                    if str.isalpha(t[0]): # a1 => a                      
                        args.append(self.symbols_graph.names2points([t])[0].num)
                    else:
                        args.append(t)
                to_be_intersected += sketch(n[0], tuple(args), self.rng)

            return reduce(
                to_be_intersected, [p.num for p in _existing_points], rng=self.rng
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
        if check_too_close_numerical(_new_numerical_point, _existing_numerical_points):
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
        if construction_def.declare[0] == 's_angle':
            points = random.sample(defined_points, len(construction_def.args) - 1)
            mapping.update(dict(zip(construction_def.args[:-1], points)))
            mapping[construction_def.args[-1]] = f'{random.choice(range(15, 180, 15))}o'
        else:
            points = random.sample(defined_points, len(construction_def.args))
            mapping.update(dict(zip(construction_def.args, points)))
        return mapping

    def construction_text(self, construction_def, mapping):
        text = f"{construction_def.declare[0]} {' '.join([mapping[p] for p in construction_def.declare[1:]])}"
        return text
    
    def prune_clauses(self, clauses: list[str]) -> list[str]:
        """Prune clauses to preserve only the deepest clause chain"""
        max_level = max(self.point_level.values())
        useful_points = [random.choice([p for p, l in self.point_level.items() if l == max_level])]
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

import re
from collections import defaultdict
def process_geometric_string(input_str):
    # 步骤1: 移除所有点定义中的坐标部分
    cleaned_str = re.sub(r'([a-z][0-9]*)@[^\s;]+', r'\1', input_str)
    # 步骤2: 计算每个点的深度
    depth_map = defaultdict(int)
    statements = [stmt.strip() for stmt in cleaned_str.split(';') if stmt.strip()]
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
        cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
        print(f'seed: {_}, Max Depth: {max_depth}, Points: {len(sorted_depths)}')
        # print(f'Clauses: {clause_text}')
        print(f'Cleaned_str: {cleaned_str}\n')

    # cc_gen = CompoundClauseGen(998)
    # clause_text = cc_gen.generate(50, prune=False)
    # print(clause_text)
    # cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
    # print(f'Max Depth: {max_depth}, Points: {len(sorted_depths)}')
    # print(f'Cleaned_str: {cleaned_str}\n')