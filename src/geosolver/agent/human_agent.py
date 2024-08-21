"""Classical Breadth-First Search based agents.

"""

from __future__ import annotations
from io import BytesIO
import tkinter as tk
from typing import TYPE_CHECKING, Any, Callable, NamedTuple, Optional
from PIL import Image, ImageTk

from geosolver.agent.agents_interface import (
    DeductiveAgent,
)
from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.definition.clause import Clause
from geosolver.numerical.draw_figure import draw_figure
from geosolver.proof import ProofState
from geosolver.rule import Rule
from numpy.random import Generator

from geosolver.statement import Statement
from geosolver.tools import atomize

if TYPE_CHECKING:
    ...


class NamedFunction(NamedTuple):
    name: str
    f: Callable[..., Any]


class HumanAgent(DeductiveAgent):
    def __init__(self, proof: ProofState, rules: list[Rule], rng: Generator) -> None:
        self.proof = proof
        self.rules = rules
        self.rng = rng
        self.match_rules = [
            NamedFunction(
                f"match {theorem.descrption}: {theorem}", self.fn_match(theorem)
            )
            for theorem in rules
        ]
        self.bfsddar: Optional[BFSDDAR] = None

    @classmethod
    def select(
        cls,
        options: list[NamedFunction],
        apply_all: bool = False,
        apply_none: bool = False,
    ) -> Any:
        for i, option in enumerate(options):
            print(f"[{i}] {option.name}")
        if apply_all:
            print("[all]")
        if apply_none:
            print("[none]")
        choice = input("Choose:")
        if choice == "all":
            for option in options:
                option.f()
        elif choice == "none":
            return
        else:
            n = int(choice)
            return options[n].f()

    def fn_match(self, rule: Rule):
        def fn():
            deps = self.proof.match_theorem(rule)
            self.select(
                [
                    NamedFunction(
                        f"{dep.statement.pretty()} <= {', '.join(s.pretty() for s in dep.why)}",
                        lambda dep=dep: self.proof.apply_dep(dep),
                    )
                    for dep in deps
                ],
                apply_all=True,
                apply_none=True,
            )

        return fn

    def match(self) -> bool:
        self.select(self.match_rules, apply_none=True)
        return True

    def show_graphics(self) -> bool:
        png_stream = BytesIO()
        draw_figure(self.proof, save_to=png_stream, rng=self.rng, format="png")

        png_stream.seek(0)
        root = tk.Tk()

        photo = ImageTk.PhotoImage(Image.open(png_stream))  # type: ignore
        label = tk.Label(root, image=photo)  # type: ignore
        label.pack()

        root.mainloop()
        return True

    def add_construction(self) -> bool:
        clauses = Clause.parse_line(input("New construction: "))
        for clause in clauses:
            self.proof.add_construction(clause)
        return True

    def exhaust_with_bfsddar(self) -> bool:
        self.bfsddar = BFSDDAR(self.proof, self.rules, self.rng)
        return True

    def check(self) -> bool:
        statement = Statement.from_tokens(
            atomize(input("Check: ")), self.proof.dep_graph
        )
        if statement is None:
            print("Statement not parsed")
        else:
            print(f"Check result of {statement.pretty()}: {statement.check()}")
        return True

    def check_goals(self) -> bool:
        selects: list[NamedFunction] = []
        for goal in self.proof.goals:
            selects.append(
                NamedFunction(
                    f"check {goal.pretty()}",
                    lambda: print(f"Check result of {goal.pretty()}: {goal.check()}"),
                )
            )
        self.select(selects, apply_all=True, apply_none=True)
        return True

    def step(self) -> bool:
        if self.bfsddar:
            res = self.bfsddar.step()
            if not res:
                self.bfsddar = None
            return True
        else:
            if not self.select(
                [
                    NamedFunction("match", self.match),
                    NamedFunction("graphics", self.show_graphics),
                    NamedFunction("construction", self.add_construction),
                    NamedFunction("exhaust with bfsddar", self.exhaust_with_bfsddar),
                    NamedFunction("check", self.check),
                    NamedFunction("check goals", self.check_goals),
                    NamedFunction("nothing", lambda: True),
                    NamedFunction("stop", lambda: False),
                ]
            ):
                for goal in self.proof.goals:
                    print(f"{goal.pretty()} proven? {goal.check()}")
                return False
            return True
