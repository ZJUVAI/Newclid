import random
import string
import numpy
import time
import logging
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
    'circumcenter',
    'eq_triangle',
    'eqangle2',
    'foot',
    # 'incenter',
    'incenter2',
    'incenter2',
    # 'excenter',
    'excenter2',
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
    'nsquare',
    'orthocenter',
    'parallelogram',
    'psquare',
    'reflect',
    'shift',
    'square',
    '2l1c',
    'e5128',
    '3peq',
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

    def generate(self, length = 0):
        self.point_generator = PointGenerator()
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.symbols_graph = self.dep_graph.symbols_graph
        self.point_level = {}
        self.point_rely = {}

        max_basic_clause = int(0.15 * length)
        res = []
        for clause_set in range(length):
            new_clause2 = None
            # step 1: add clause with basic 
            if len(res) == 0: 
                new_clause = self.get_clause_with_n_constructions(BASIC, 1)
            # step 2: add clause with basic (free) 
            # elif clause_set < max_basic_clause:
            #     new_clause = self.get_clause_with_n_constructions(BASIC_FREE, 1)
            # step 3: add cluase with single constructions or two constructions
            else:
                if random.random() < 0.5:
                    new_clause, new_clause2 = self.get_clause_with_n_constructions(INTERSECT, 2)
                    # print(new_clause, new_clause2)
                    # import pdb; pdb.set_trace()
                else:
                    new_clause = self.get_clause_with_n_constructions(OTHER+INTERSECT+BASIC_FREE, 1)
            if new_clause:
                res.append(new_clause)
                if res[0].split("=")[1].strip().split(" ")[0] in ['triangle', 'triangle12', 'r_triangle', 'iso_triangle', 'ieq_triangle']:
                    new_consts = re.findall(r'(?:=|,)\s*([A-Za-z_][A-Za-z0-9_]*)', new_clause)
                    for new_const in new_consts:
                        if new_const == 'midpoint':
                            new_clause_ = self.get_clause_with_n_constructions2(['midpoint'], ['a', 'b'])
                            if new_clause_: res.append(new_clause_)
                            new_clause_ = self.get_clause_with_n_constructions2(['midpoint'], ['b', 'c'])
                            if new_clause_: res.append(new_clause_)
                            new_clause_ = self.get_clause_with_n_constructions2(['midpoint'], ['a', 'c'])
                            if new_clause_: res.append(new_clause_)
                        if new_const == 'orthocenter':
                            new_clause_ = self.get_clause_with_n_constructions2(['orthocenter'], ['a', 'b', 'c'])
                            if new_clause_: res.append(new_clause_)
                            new_clause_ = self.get_clause_with_n_constructions2(['foot'], ['a', 'b', 'c'])
                            if new_clause_: res.append(new_clause_)
                            new_clause = self.get_clause_with_n_constructions2(['foot'], ['b', 'a', 'c'])
                            if new_clause_: res.append(new_clause_)
                            new_clause_ = self.get_clause_with_n_constructions2(['foot'], ['c', 'a', 'b'])
                            if new_clause_: res.append(new_clause_)
                        if new_const in ['circle', 'incenter2', 'excenter2']:
                            new_clause_ = self.get_clause_with_n_constructions2([new_const], ['a', 'b', 'c'])
                            if new_clause_: res.append(new_clause_)
                #         # print(res)
                #         # import pdb; pdb.set_trace()
            if new_clause2:
                res.append(new_clause2)        
        res = self.prune_clauses(res)
        return "; ".join(res)

    def get_clause_with_n_constructions(self, construction_candidates, n: int):
        try_count = 0
        while try_count < 10:
            try_count += 1
            # samples constructions
            constructions = []
            numerics = []
            max_level = -1
            rely_points = set()

            constructions2 = []
            numerics2 = []
            max_level = -1
            rely_points2 = set()
            try:
                if n == 1:
                    new_points, construction, numeric = self.choose_construction(construction_candidates)
                    constructions.append(construction)
                    numerics += numeric
                    max_level = max([max_level] + [self.point_level.get(p, -1) for p in construction.split()[1:]])
                    rely_points.update([p for p in construction.split()[1:] if p in self.point_rely])
                    # check numerics by drawing diagram
                    self.draw_diagram(new_points, numerics)

                    self.point_generator.define_points(new_points)
                    # output clause str. add xy for new points to accelerate building
                    new_points_str=[]
                    for p in new_points:
                        p_num = self.symbols_graph.names2points([p])[0]
                        new_points_str.append(f'{p}@{p_num.num.x}_{p_num.num.y}')
                        self.point_level[p] = max_level + 1
                        self.point_rely[p] = rely_points
                    return ' '.join(new_points_str) + " = " + ', '.join(constructions)
                else:
                    # multiple n_constructions shares the same new points. Only support one new point
                    new_points = self.point_generator.prefetch_points(2)
                    for _ in range(n):
                        resA, resB = self.choose_construction3(construction_candidates, new_points)
                        
                        _, construction, numeric = resA
                        constructions.append(construction)
                        numerics += numeric
                        max_level = max([max_level] + [self.point_level.get(p, -1) for p in construction.split()[1:]])
                        rely_points.update([p for p in construction.split()[1:] if p in self.point_rely])
                        

                        _, construction, numeric = resB
                        constructions2.append(construction)
                        numerics2 += numeric
                        # max_level = max([max_level] + [self.point_level.get(p, -1) for p in construction.split()[1:]])
                        rely_points2.update([p for p in construction.split()[1:] if p in self.point_rely])
                    # check numerics by drawing diagram
                    self.draw_diagram(new_points[0:1], numerics)
                    self.point_generator.define_points(new_points[0:1])
                    new_points_str=[]
                    for p in new_points[0:1]:
                        p_num = self.symbols_graph.names2points([p])[0]
                        new_points_str.append(f'{p}@{p_num.num.x}_{p_num.num.y}')
                        self.point_level[p] = max_level + 1
                        self.point_rely[p] = rely_points
                    res1 = ' '.join(new_points_str) + " = " + ', '.join(constructions)


                    try:
                        # check numerics by drawing diagram
                        self.draw_diagram(new_points[1:2], numerics)
                        self.point_generator.define_points(new_points[1:2])
                    except Exception as e:
                        return res1, None
                    new_points_str=[]
                    for p in new_points[1:2]:
                        p_num = self.symbols_graph.names2points([p])[0]
                        new_points_str.append(f'{p}@{p_num.num.x}_{p_num.num.y}')
                        self.point_level[p] = max_level + 1
                        self.point_rely[p] = rely_points2
                    res2 =  ' '.join(new_points_str) + " = " + ', '.join(constructions2)

                    # import pdb; pdb.set_trace()
                    return res1, res2
                

                
            except Exception as e:
                # print(f"Exception type: {type(e).__name__}, message: {e}")
                # import traceback
                # traceback.print_exc()
                continue
        
        if n == 1:
            return None
        if n == 2:
            return None, None
            
    def get_clause_with_n_constructions2(self, construction_candidates, rpoints):
        try_count = 0
        while try_count < 10:
            try_count += 1
            # samples constructions
            constructions = []
            numerics = []
            max_level = -1
            rely_points = set()
            try:
                new_points, construction, numeric = self.choose_construction2(construction_candidates, rpoints)
                # import pdb; pdb.set_trace()
                constructions.append(construction)
                numerics += numeric
                max_level = max([max_level] + [self.point_level.get(p, -1) for p in construction.split()[1:]])
                rely_points.update([p for p in construction.split()[1:] if p in self.point_rely])
                # check numerics by drawing diagram
                self.draw_diagram(new_points, numerics)
            except Exception as e:
                # print(f"Exception type: {type(e).__name__}, message: {e}")
                # import traceback
                # traceback.print_exc()
                continue

            self.point_generator.define_points(new_points)
            # output clause str. add xy for new points to accelerate building
            new_points_str=[]
            for p in new_points:
                p_num = self.symbols_graph.names2points([p])[0]
                new_points_str.append(f'{p}@{p_num.num.x}_{p_num.num.y}')
                self.point_level[p] = max_level + 1
                self.point_rely[p] = rely_points
            return ' '.join(new_points_str) + " = " + ', '.join(constructions)
    def choose_construction2(self, construction_candidates, rely_points, new_points = None):
        random_construction_candidates = construction_candidates.copy()
        self.rng.shuffle(random_construction_candidates)
        for construction in random_construction_candidates:
            construction_def = self.defs[construction]

            # create new point if new_points is None
            if not new_points:
                new_points = self.point_generator.prefetch_points(len(construction_def.points))

            # check number of points
            if len(construction_def.points) != len(new_points):
                continue
            if len(construction_def.args) > len(rely_points):
                continue

            # create mapping
            mapping = self.map_points(construction_def, rely_points, new_points)

            # check construction requirements
            try:
                for premise in construction_def.require.sentences:
                    if len(premise) == 0:
                        continue
                    statement = Statement.from_tokens(translate_sentence(mapping, premise), self.dep_graph)
                    if statement is None or not statement.check_numerical():
                        raise ConstructionError("Requirement check_numerical failed. " + str(construction))
            except Exception as e:
                continue
            try:
                for bs in construction_def.basics:
                    for t in bs.sentences:
                        statement = Statement.from_tokens(translate_sentence(mapping, t), self.dep_graph)
            except Exception as e:
                logging.warning(f"Error processing construction {construction}: {e}")
                continue

            # output numerics for draw check
            numerics = []
            for n in construction_def.numerics:
                numerics.append(tuple(mapping[a] if a in mapping else a for a in n))

            return new_points, self.construction_text(construction_def, mapping), numerics
        
        raise ConstructionError("No valid construction found.")
    
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
            
    def choose_construction(self, construction_candidates, new_points = None):
        random_construction_candidates = construction_candidates.copy()
        self.rng.shuffle(random_construction_candidates)
        for construction in random_construction_candidates:
            construction_def = self.defs[construction]

            # create new point if new_points is None
            if not new_points:
                new_points = self.point_generator.prefetch_points(len(construction_def.points))

            # check number of points
            if len(construction_def.points) != len(new_points):
                continue
            if len(construction_def.args) > len(self.point_generator.defined_points):
                continue

            # create mapping
            mapping = self.map_points(construction_def, self.point_generator.defined_points, new_points)

            # check construction requirements
            try:
                for premise in construction_def.require.sentences:
                    if len(premise) == 0:
                        continue
                    statement = Statement.from_tokens(translate_sentence(mapping, premise), self.dep_graph)
                    if statement is None or not statement.check_numerical():
                        raise ConstructionError("Requirement check_numerical failed. " + str(construction))
            except Exception as e:
                continue
            try:
                for bs in construction_def.basics:
                    for t in bs.sentences:
                        statement = Statement.from_tokens(translate_sentence(mapping, t), self.dep_graph)
            except Exception as e:
                logging.warning(f"Error processing construction {construction}: {e}")
                continue

            # output numerics for draw check
            numerics = []
            for n in construction_def.numerics:
                numerics.append(tuple(mapping[a] if a in mapping else a for a in n))

            return new_points, self.construction_text(construction_def, mapping), numerics
        
        raise ConstructionError("No valid construction found.")
    
    def choose_construction3(self, construction_candidates, new_points = None):
        random_construction_candidates = construction_candidates.copy()
        self.rng.shuffle(random_construction_candidates)
        for construction in random_construction_candidates:
            construction_def = self.defs[construction]

            # create new point if new_points is None
            if not new_points:
                new_points = self.point_generator.prefetch_points(len(construction_def.points))

            # check number of points
            if len(construction_def.points) != len(new_points[0:1]):
                continue
            if len(construction_def.args) > len(self.point_generator.defined_points):
                continue
            

            # create mapping
            mappingA = self.map_points(construction_def, self.point_generator.defined_points, new_points[0:1])
            

            # check construction requirements
            try:
                for premise in construction_def.require.sentences:
                    if len(premise) == 0:
                        continue
                    statement = Statement.from_tokens(translate_sentence(mappingA, premise), self.dep_graph)
                    if statement is None or not statement.check_numerical():
                        raise ConstructionError("Requirement check_numerical failed. " + str(construction))
            except Exception as e:
                continue
            try:
                for bs in construction_def.basics:
                    for t in bs.sentences:
                        statement = Statement.from_tokens(translate_sentence(mappingA, t), self.dep_graph)
            except Exception as e:
                logging.warning(f"Error processing construction {construction}: {e}")
                continue

            # output numerics for draw check
            numerics = []
            for n in construction_def.numerics:
                numerics.append(tuple(mappingA[a] if a in mappingA else a for a in n))
            resA = [new_points[0:1], self.construction_text(construction_def, mappingA), numerics]
            
            #------------------
            # mappingB = self.map_points(construction_def, self.point_generator.defined_points, new_points[1:2])
            old, new = new_points  # old = 'f', new = 'g'
            for k, v in mappingA.items():
                if v == old:
                    mappingA[k] = new
                    break   # 只替换第一个
            mappingB = mappingA
            # import pdb; pdb.set_trace()
            # check construction requirements
            try:
                for premise in construction_def.require.sentences:
                    if len(premise) == 0:
                        continue
                    statement = Statement.from_tokens(translate_sentence(mappingB, premise), self.dep_graph)
                    if statement is None or not statement.check_numerical():
                        raise ConstructionError("Requirement check_numerical failed. " + str(construction))
            except Exception as e:
                continue
            try:
                for bs in construction_def.basics:
                    for t in bs.sentences:
                        statement = Statement.from_tokens(translate_sentence(mappingB, t), self.dep_graph)
            except Exception as e:
                logging.warning(f"Error processing construction {construction}: {e}")
                continue

            # output numerics for draw check
            numerics = []
            for n in construction_def.numerics:
                numerics.append(tuple(mappingB[a] if a in mappingB else a for a in n))
            resB = [new_points[1:2], self.construction_text(construction_def, mappingB), numerics]


            return resA, resB
            
        
        raise ConstructionError("No valid construction found.")
        
    
    def map_points(self, construction_def, defined_points, new_points):
        # mapping point to new points
        mapping = dict(zip(construction_def.points, new_points))
        # mapping args to predefined_points
        if construction_def.declare[0] in ['s_angle']:
            points = random.sample(defined_points, len(construction_def.args) - 1)
            for i, point in enumerate(points):
                mapping[construction_def.args[i]] = point
            if construction_def.declare[0] == 's_angle':
                mapping[construction_def.args[-1]] = f'{random.choice(range(15, 180, 15))}o'
        else:
            points = random.sample(defined_points, len(construction_def.args))
            for i, point in enumerate(points):
                mapping[construction_def.args[i]] = point
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
    count=1000
    sum = 0
    for i in range(count):
        clause_text = cc_gen.generate(15)
        cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
        sum += len(sorted_depths)
    print(sum/count)

    sum = 0
    for i in range(count):
        clause_text = cc_gen.generate(30)
        cleaned_str, sorted_depths, max_depth = process_geometric_string(clause_text)
        sum += len(sorted_depths)
    print(sum/count)

    import pdb; pdb.set_trace()
    clause_text = cc_gen.generate(15)
    clause_text = cc_gen.generate(50)
    clause_text = cc_gen.generate(50)
    print(clause_text)
    for i in range(20):
        s_time = time.time()
        cc_gen = CompoundClauseGen(i)
        clause_text = cc_gen.generate(50)
        print(f'{time.time() - s_time:.2f}s')
