# Copyright 2023 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Implements objects to represent problems, theorems, proofs, traceback."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any


from geosolver.predicates import Predicate
from geosolver.dependencies.caching import hashed_txt

import geosolver.geometry as gm
import geosolver.pretty as pt

from geosolver.ratios import simplify

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency

CONSTRUCTION_RULE = "c0"


def reshape(list_to_reshape: list[Any], n: int = 1) -> list[list[Any]]:
    assert len(list_to_reshape) % n == 0
    columns = [[] for i in range(n)]
    for i, x in enumerate(list_to_reshape):
        columns[i % n].append(x)
    return zip(*columns)


class Construction:
    """One predicate."""

    @classmethod
    def from_txt(cls, data: str) -> Construction:
        data = data.split(" ")
        return Construction(data[0], data[1:])

    def __init__(self, name: str, args: list[str | gm.Point]):
        self.name = name
        self.args = args

    def translate(self, mapping: dict[str, str]) -> Construction:
        args = [mapping[a] if a in mapping else a for a in self.args]
        return Construction(self.name, args)

    def txt(self) -> str:
        return name_and_arguments_to_str(self.name, self.args, " ")

    def __str__(self) -> str:
        return self.txt()


class Clause:
    """One construction (>= 1 predicate)."""

    @classmethod
    def from_txt(cls, data: str) -> Clause:
        if data == " =":
            return Clause([], [])
        points, constructions = data.split(" = ")
        return Clause(
            points.split(" "),
            [Construction.from_txt(c) for c in constructions.split(", ")],
        )

    def __init__(self, points: list[str], constructions: list[Construction]):
        self.points = []
        self.nums = []

        for p in points:
            num = None
            if isinstance(p, str) and "@" in p:
                p, num = p.split("@")
                x, y = num.split("_")
                num = float(x), float(y)
            self.points.append(p)
            self.nums.append(num)

        self.constructions = constructions

    def translate(self, mapping: dict[str, str]) -> Clause:
        points0 = []
        for p in self.points:
            pcount = len(mapping) + 1
            name = chr(96 + pcount)
            if name > "z":  # pcount = 26 -> name = 'z'
                name = chr(97 + (pcount - 1) % 26) + str((pcount - 1) // 26)

            p0 = mapping.get(p, name)
            mapping[p] = p0
            points0.append(p0)
        return Clause(points0, [c.translate(mapping) for c in self.constructions])

    def add(self, name: str, args: list[str]) -> None:
        self.constructions.append(Construction(name, args))

    def txt(self) -> str:
        return (
            " ".join(self.points)
            + " = "
            + ", ".join(c.txt() for c in self.constructions)
        )


def compare_fn(dep: "Dependency") -> tuple["Dependency", str]:
    return (dep, pt.pretty(dep))


def sort_deps(deps: list["Dependency"]) -> list["Dependency"]:
    return sorted(deps, key=compare_fn)


def name_and_arguments_to_str(
    name: str, args: list[str | int | "gm.Node"], join: str
) -> list[str]:
    return join.join([name] + arguments_to_str(args))


def arguments_to_str(args: list[str | int | "gm.Node"]) -> list[str]:
    args_str = []
    for arg in args:
        if isinstance(arg, (int, str, float)):
            args_str.append(str(arg))
        else:
            args_str.append(arg.name)
    return args_str


class Problem:
    """Describe one problem to solve."""

    @classmethod
    def from_txt_file(cls, fname: str, to_dict: bool = False, translate: bool = True):
        """Load a problem from a text file."""
        with open(fname, "r") as f:
            lines = f.read().split("\n")

        lines = [line for line in lines if line]
        data = [
            cls.from_txt(url + "\n" + problem, translate)
            for (url, problem) in reshape(lines, 2)
        ]
        if to_dict:
            return cls.to_dict(data)
        return data

    @classmethod
    def from_txt(cls, data: str, translate: bool = True) -> Problem:
        """Load a problem from a str object."""
        url = ""
        if "\n" in data:
            url, data = data.split("\n")

        if " ? " in data:
            clauses, goal = data.split(" ? ")
            goal = Construction.from_txt(goal)
        else:
            clauses, goal = data, None

        clauses = clauses.split("; ")
        problem = Problem(
            url=url, clauses=[Clause.from_txt(c) for c in clauses], goal=goal
        )
        if translate:
            return problem.translate()
        return problem

    @classmethod
    def to_dict(cls, data: list[Problem]) -> dict[str, Problem]:
        return {p.url: p for p in data}

    def __init__(self, url: str, clauses: list[Clause], goal: Construction):
        self.url = url
        self.clauses = clauses
        self.goal = goal

    def copy(self) -> Problem:
        return Problem(self.url, list(self.clauses), self.goal)

    def translate(self) -> Problem:  # to single-char point names
        """Translate point names into alphabetical."""
        mapping = {}
        clauses = []

        for clause in self.clauses:
            clauses.append(clause.translate(mapping))

        if self.goal:
            goal = self.goal.translate(mapping)
        else:
            goal = self.goal

        p = Problem(self.url, clauses, goal)
        p.mapping = mapping
        return p

    def txt(self) -> str:
        return "; ".join([c.txt() for c in self.clauses]) + (
            " ? " + self.goal.txt() if self.goal else ""
        )

    def setup_str_from_problem(self, definitions: list[Definition]) -> str:
        """Construct the <theorem_premises> string from Problem object."""
        ref = 0

        string = []
        for clause in self.clauses:
            group = {}
            p2deps = defaultdict(list)
            for c in clause.constructions:
                cdef = definitions[c.name]

                if len(c.args) != len(cdef.construction.args):
                    assert len(c.args) + len(clause.points) == len(
                        cdef.construction.args
                    )
                    c.args = clause.points + c.args

                mapping = dict(zip(cdef.construction.args, c.args))
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    for p in points:
                        group[p] = points

                    for b in bs:
                        args = [mapping[a] for a in b.args]
                        name = b.name
                        if b.name in [
                            Predicate.S_ANGLE.value,
                            Predicate.CONSTANT_ANGLE.value,
                        ]:
                            x, y, z, v = args
                            name = Predicate.CONSTANT_ANGLE.value
                            v = int(v)

                            if v < 0:
                                v = -v
                                x, z = z, x

                            m, n = simplify(int(v), 180)
                            args = [y, z, y, x, f"{m}pi/{n}"]

                        p2deps[points].append(hashed_txt(name, args))

            for k, v in p2deps.items():
                p2deps[k] = sort_deps(v)

            points = clause.points
            while points:
                p = points[0]
                gr = group[p]
                points = [x for x in points if x not in gr]

                deps_str = []
                for dep in p2deps[gr]:
                    ref_str = "{:02}".format(ref)
                    dep_str = pt.pretty(dep)

                    if dep[0] == Predicate.CONSTANT_ANGLE.value:
                        m, n = map(int, dep[-1].split("pi/"))
                        mn = f"{m}. pi / {n}."
                        dep_str = " ".join(dep_str.split()[:-1] + [mn])

                    deps_str.append(dep_str + " " + ref_str)
                    ref += 1

                string.append(" ".join(gr) + " : " + " ".join(deps_str))

        string = "{S} " + " ; ".join([s.strip() for s in string])
        goal = self.goal
        string += " ? " + pt.pretty([goal.name] + goal.args)
        return string


def parse_rely(s: str) -> dict[str, str]:
    result = {}
    if not s:
        return result
    s = [x.strip() for x in s.split(",")]
    for x in s:
        a, b = x.split(":")
        a, b = a.strip().split(), b.strip().split()
        result.update({m: b for m in a})
    return result


class Definition:
    """Definitions of construction statements."""

    @classmethod
    def from_txt_file(cls, fname: str) -> Definition:
        with open(fname, "r") as f:
            lines = f.read()
        return cls.from_string(lines)

    @classmethod
    def from_string(cls, string: str) -> Definition:
        lines = string.split("\n")
        data = [cls.from_txt("\n".join(group)) for group in reshape(lines, 6)]
        return data

    @staticmethod
    def to_dict(data: list[Definition]) -> dict[str, Definition]:
        return {d.construction.name: d for d in data}

    @classmethod
    def from_txt(cls, data: str) -> Definition:
        """Load definitions from a str object."""
        construction, rely, deps, basics, numerics, _ = data.split("\n")
        basics = [] if not basics else [b.strip() for b in basics.split(";")]

        levels = []
        for bs in basics:
            if ":" in bs:
                points, bs = bs.split(":")
                points = points.strip().split()
            else:
                points = []
            if bs.strip():
                bs = [Construction.from_txt(b.strip()) for b in bs.strip().split(",")]
            else:
                bs = []
            levels.append((points, bs))

        numerics = [] if not numerics else numerics.split(", ")

        return cls(
            construction=Construction.from_txt(construction),
            rely=parse_rely(rely),
            deps=Clause.from_txt(deps),
            basics=levels,
            numerics=[Construction.from_txt(c) for c in numerics],
        )

    def __init__(
        self,
        construction: Construction,
        rely: dict[str, str],
        deps: Clause,
        basics: list[tuple[list[str], list[Construction]]],
        numerics: list[Construction],
    ):
        self.construction = construction
        self.rely = rely
        self.deps = deps
        self.basics = basics
        self.numerics = numerics

        args = set()
        for num in numerics:
            args.update(num.args)

        self.points = []
        self.args = []
        for p in self.construction.args:
            if p in args:
                self.args.append(p)
            else:
                self.points.append(p)


class Theorem:
    """Deduction rule."""

    @classmethod
    def from_txt_file(cls, fname: str) -> list[Theorem]:
        with open(fname, "r") as f:
            theorems = f.read()
        return cls.from_string(theorems)

    @classmethod
    def from_string(cls, string: str) -> list[Theorem]:
        """Load deduction rule from a str object."""
        theorems = string.split("\n")
        theorems = [line for line in theorems if line and not line.startswith("#")]
        theorems = [cls.from_txt(line) for line in theorems]

        for i, th in enumerate(theorems):
            th.rule_name = "r{:02}".format(i)

        return theorems

    @staticmethod
    def to_dict(theorems: list[Theorem]):
        result = {}
        for t in theorems:
            if t.name in result:
                t.name += "_"
            result[t.rule_name] = t
        return result

    @classmethod
    def from_txt(cls, data: str) -> Theorem:
        premises, conclusion = data.split(" => ")
        premises = premises.split(", ")
        conclusion = conclusion.split(", ")
        return Theorem(
            premise=[Construction.from_txt(p) for p in premises],
            conclusion=[Construction.from_txt(c) for c in conclusion],
        )

    def __init__(self, premise: list[Construction], conclusion: list[Construction]):
        if len(conclusion) != 1:
            raise ValueError("Cannot have more or less than one conclusion")
        self.name = "_".join([p.name for p in premise + conclusion])
        self.rule_name = None
        self.premise = premise
        self.is_arg_reduce = False
        self.conclusion = conclusion[0]

        if self.conclusion.name in [
            Predicate.EQRATIO3.value,
            Predicate.MIDPOINT.value,
            Predicate.CONTRI_TRIANGLE.value,
            Predicate.SIMILAR_TRIANGLE.value,
            Predicate.CONTRI_TRIANGLE_REFLECTED.value,
            Predicate.SIMILAR_TRIANGLE_REFLECTED.value,
            Predicate.SIMILAR_TRIANGLE_BOTH.value,
            Predicate.CONTRI_TRIANGLE_BOTH.value,
        ]:
            return

        prem_args = set(sum([p.args for p in self.premise], []))
        con_args = set(self.conclusion.args)
        if len(prem_args) <= len(con_args):
            self.is_arg_reduce = True

    def txt(self) -> str:
        premise_txt = ", ".join([clause.txt() for clause in self.premise])
        conclusion_txt = ", ".join([self.conclusion.txt()])
        return f"{premise_txt} => {conclusion_txt}"
