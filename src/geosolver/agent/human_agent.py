"""Classical Breadth-First Search based agents.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, NamedTuple

from geosolver.agent.agents_interface import (
    ApplyTheoremAction,
    DeductiveAgent,
    Action,
    EmptyAction,
    Feedback,
    MatchAction,
    MatchFeedback,
    StopAction,
)

if TYPE_CHECKING:
    from geosolver.theorem import Theorem
    from geosolver.definition.definition import Definition


class NamedFunction(NamedTuple):
    name: str
    f: Callable[..., Any]


class HumanAgent(DeductiveAgent):
    """ """

    def __init__(
        self, defs: dict[str, "Definition"], theorems: list["Theorem"]
    ) -> None:
        self.defs = defs
        self.theorems = theorems
        self.match_theorems: list[NamedFunction] = []
        self.apply_buffer: list[ApplyTheoremAction] = []
        self.match_theorems = [
            NamedFunction(
                f"match {theorem.descrption}: {theorem}",
                lambda theorem=theorem: MatchAction(theorem),
            )
            for theorem in theorems
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

    def match(self) -> Action:
        action = self.select(self.match_theorems)
        return action

    def act(self) -> Action:
        if self.apply_buffer:
            return self.apply_buffer.pop()
        return self.select(
            [
                NamedFunction("match", self.match),
                NamedFunction("nothing", lambda: EmptyAction()),
                NamedFunction("stop", lambda: StopAction()),
            ]
        )

    def remember_effects(self, action: Action, feedback: Feedback) -> None:
        if isinstance(feedback, MatchFeedback):
            self.select(
                [
                    NamedFunction(
                        str(dep),
                        lambda dep=dep: self.apply_buffer.append(
                            ApplyTheoremAction(dep)
                        ),
                    )
                    for dep in feedback.deps
                ],
                apply_all=True,
                apply_none=True,
            )
