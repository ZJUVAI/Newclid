"""Classical Breadth-First Search based agents."""

from __future__ import annotations
from functools import partial
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

from newclid import webapp
from newclid.agent.agents_interface import (
    DeductiveAgent,
)
from newclid.agent.ddarn import DDARN
from newclid.formulations.clause import Clause
from newclid.proof import ProofState
from newclid.formulations.rule import Rule

from newclid.statement import Statement
from newclid.tools import atomize, run_static_server


class NamedFunction(NamedTuple):
    name: str
    function: Callable[..., Any]


class HumanAgent(DeductiveAgent):
    def __init__(self):
        self.ddarn: Optional[DDARN] = None
        self.server: Optional[Path] = None

    @classmethod
    def select(
        cls,
        options: list[NamedFunction],
        allow_all: bool = False,
        allow_none: bool = False,
    ) -> NamedFunction | None:
        options_string = "\nSelect an option:"
        for i, option in enumerate(options):
            options_string += f"\n- [{i}] {option.name}"
        if allow_all:
            options_string += "- [all]"
        if allow_none:
            options_string += "- [none]"

        options_string += "\nChoose:"
        choice = input(options_string)
        if choice == "all":
            for option in options:
                option.function()
            return
        if choice == "none":
            return
        n = int(choice)
        return options[n]

    def step(self, proof: ProofState, rules: list[Rule]) -> bool:
        exausted = False
        match_rules = [
            NamedFunction(
                f"match {theorem.descrption}: {theorem}", self._fn_match(proof, theorem)
            )
            for theorem in rules
        ]
        if self.ddarn:
            if not self.ddarn.step(proof=proof, rules=rules):
                self.ddarn = None
        else:
            print("Premises:")
            for dep in proof.dep_graph.premises():
                print(f"{dep.statement.pretty()}")
            selected = self.select(
                [
                    NamedFunction(
                        "match", partial(self.match, match_rules=match_rules)
                    ),
                    NamedFunction(
                        "update server", partial(self.update_server, proof=proof)
                    ),
                    NamedFunction(
                        "construction", partial(self.add_construction, proof=proof)
                    ),
                    NamedFunction("exhaust with ddarn", self.exhaust_with_ddarn),
                    NamedFunction("check statement", partial(self.check, proof=proof)),
                    NamedFunction(
                        "check goals", partial(self.check_goals, proof=proof)
                    ),
                    NamedFunction("stop", lambda: None),
                ],
                allow_none=True,
            )
            if selected is None:
                return not exausted
            selected.function()
            if selected.name == "stop":
                exausted = True
        if proof.check_goals():
            print("All the goals are proven")
        else:
            for goal in proof.goals:
                print(f"{goal.pretty()} proven? {goal.check()}")
        return not exausted

    def match(self, match_rules: list[NamedFunction]) -> None:
        selected = self.select(match_rules, allow_none=True)
        if selected is not None:
            selected.function()

    def update_server(self, proof: "ProofState") -> None:
        self._pull_to_server(proof)

    def add_construction(self, proof: "ProofState") -> None:
        clauses = Clause.parse_line(input("New construction: "))
        for clause in clauses:
            proof.add_construction(clause)

    def exhaust_with_ddarn(self) -> None:
        self.ddarn = DDARN()

    def check(self, proof: "ProofState") -> None:
        statement = Statement.from_tokens(atomize(input("Check: ")), proof.dep_graph)
        if statement is None:
            print("Statement not parsed")
        else:
            print(f"Check result of {statement.pretty()}: {statement.check()}")

    def check_goals(self, proof: "ProofState") -> None:
        selects: list[NamedFunction] = [
            NamedFunction(
                f"check {goal.pretty()}",
                lambda: print(f"Check result of {goal.pretty()}: {goal.check()}"),
            )
            for goal in proof.goals
        ]
        selected = self.select(selects, allow_all=True, allow_none=True)
        if selected is not None:
            selected.function()

    def _pull_to_server(self, proof: "ProofState"):
        assert proof.problem_path
        if not self.server:
            self.server = proof.problem_path / "html"
            run_static_server(self.server)
        webapp.pull_to_server(proof, server_path=self.server)

    def _fn_match(self, proof: "ProofState", rule: Rule):
        def fn():
            deps = proof.match_theorem(rule)
            selected = self.select(
                [
                    NamedFunction(
                        f"{', '.join(s.pretty() for s in dep.why)} => {dep.statement.pretty()}",
                        lambda dep=dep: proof.apply_dep(dep),
                    )
                    for dep in deps
                ],
                allow_all=True,
                allow_none=True,
            )
            if selected is None:
                return
            return selected.function

        return fn
