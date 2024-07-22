"""Classical Breadth-First Search based agents.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, NamedTuple

from geosolver.agent.agents_interface import (
    DeductiveAgent,
)
from geosolver.proof import Proof
from geosolver.rule import Rule

if TYPE_CHECKING:
    ...


class NamedFunction(NamedTuple):
    name: str
    f: Callable[..., Any]


class HumanAgent(DeductiveAgent):
    def __init__(self, proof: Proof, rules: list[Rule]) -> None:
        self.proof = proof
        self.rules = rules
        self.match_rules = [
            NamedFunction(
                f"match {theorem.descrption}: {theorem}", self.fn_match(theorem)
            )
            for theorem in rules
        ]

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

    def step(self) -> bool:
        return self.select(
            [
                NamedFunction("match", self.match),
                NamedFunction("nothing", lambda: True),
                NamedFunction("stop", lambda: False),
            ]
        )
