from __future__ import annotations
from typing import NamedTuple, Optional, TypeVar

from geosolver.statement import Statement
from geosolver.theorem import Theorem
from geosolver.agent.interface import (
    Action,
    ApplyDerivationAction,
    ApplyDerivationFeedback,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    AuxAction,
    AuxFeedback,
    DeductiveAgent,
    DeriveAlgebraAction,
    DeriveFeedback,
    Feedback,
    Mapping,
    MatchAction,
    MatchFeedback,
    ResetAction,
    ResetFeedback,
    StopAction,
    StopFeedback,
)
from geosolver.predicates import Predicate
from geosolver.dependencies.dependency import Dependency
from geosolver.geometry import Point
from geosolver.problem import Problem
from geosolver.proof import Proof, theorem_mapping_str
from geosolver.statements.adder import ToCache

from colorama import just_fix_windows_console
from colorama import Fore, Style

just_fix_windows_console()

T = TypeVar("T")


class ShowAction(NamedTuple):
    pass


class HumanAgent(DeductiveAgent):
    INPUT_TO_ACTION_TYPE = {
        "show": ShowAction,
        "match": MatchAction,
        "apply": ApplyTheoremAction,
        "resolve derivations": DeriveAlgebraAction,
        "derive": ApplyDerivationAction,
        "aux": AuxAction,
        "stop": StopAction,
    }
    ACTION_TYPE_DESCRIPTION = {
        MatchAction: "Match a theorem to know on which mappings it can be applied.",
        StopAction: "Stop the proof",
        ApplyTheoremAction: "Apply a theorem on a mapping of points.",
        DeriveAlgebraAction: "Resolve available derivation from current proof state.",
        ApplyDerivationAction: "Apply a derivation.",
        AuxAction: "Add an auxiliary construction to the setup.",
        ShowAction: "Show the geometric figure of the current proof.",
    }

    def __init__(self) -> None:
        super().__init__()
        self._mappings: dict[str, tuple[Theorem, Mapping]] = {}
        self._known_mappings: set[str] = set()

        self._derivations: dict[str, tuple[Statement, Dependency]] = {}
        self._known_derivations: set[Statement] = set()

        self._all_added: list[Statement] = []
        self._all_cached: list[Statement] = []

        self.level = 0
        self._problem: Optional[Problem] = None

    def act(self, proof: Proof, theorems: list[Theorem]) -> Action:
        ACTION_TYPE_ACT = {
            StopAction: self._act_stop,
            MatchAction: self._act_match,
            ApplyTheoremAction: self._act_apply_theorem,
            DeriveAlgebraAction: self._act_resolve_derivations,
            ApplyDerivationAction: self._act_apply_derivation,
            AuxAction: self._act_aux,
            ShowAction: self._act_show,
        }

        action = None
        while action is None:
            choosen_action_type = self._choose_action_type()
            act_method = ACTION_TYPE_ACT[choosen_action_type]
            action = act_method(theorems)
            if isinstance(action, ShowAction):
                action = self._show_figure(proof)

        if isinstance(action, (ApplyTheoremAction, ApplyDerivationAction)):
            self.level += 1
        return action

    def _act_show(self, theorems: list[Theorem]):
        return ShowAction()

    def _act_stop(self, theorems: list[Theorem]) -> StopAction:
        return StopAction()

    def _act_match(self, theorems: list[Theorem]) -> MatchAction:
        choose_theorem_str = "\nChoose a theorem: \n"
        for th in theorems:
            choose_theorem_str += f" - [{th.rule_name}]: {th}\n"
        choose_theorem_str += (
            "Theorem you want to match (type only the name within brackets): "
        )
        theorem_dict = {th.rule_name: th for th in theorems}
        theorem = self._ask_for_key(theorem_dict, choose_theorem_str)
        return MatchAction(theorem, level=self.level)

    def _act_apply_theorem(self, theorems: list[Theorem]) -> ApplyTheoremAction:
        choosen_mapping_str = "\nAvailable theorems mappings: \n"
        for mapping_str in self._mappings.keys():
            choosen_mapping_str += f" - [{mapping_str}]\n"
        choosen_mapping_str += "Mapping you want to apply: "
        theorem, mapping = self._ask_for_key(
            self._mappings, choosen_mapping_str, pop=True
        )
        return ApplyTheoremAction(theorem, mapping)

    def _act_resolve_derivations(self, theorems: list[Theorem]) -> DeriveAlgebraAction:
        return DeriveAlgebraAction(level=self.level)

    def _act_apply_derivation(self, theorems: list[Theorem]) -> ApplyDerivationAction:
        choose_derivation_str = "\nAvailable derivations: \n"
        for derived_statement_str in self._derivations.keys():
            choose_derivation_str += f" - [{derived_statement_str}]\n"
        choose_derivation_str += "Derivation you want to apply: "
        derived_statement, reason = self._ask_for_key(
            self._derivations, choose_derivation_str, pop=True
        )
        return ApplyDerivationAction(statement=derived_statement, reason=reason)

    def _act_aux(self, theorems: list[Theorem]) -> AuxAction:
        aux_string = self._ask_input("Auxiliary string: ")
        return AuxAction(aux_string)

    def remember_effects(self, action: Action, feedback: Feedback):
        feedback_type_to_method = {
            ResetFeedback: self._remember_reset,
            StopFeedback: self._remember_stop,
            MatchFeedback: self._remember_match,
            ApplyTheoremFeedback: self._remember_apply_theorem,
            DeriveFeedback: self._remember_derivations,
            ApplyDerivationFeedback: self._remember_apply_derivation,
            AuxFeedback: self._remember_aux,
        }

        for feedback_type, feedback_process in feedback_type_to_method.items():
            if isinstance(feedback, feedback_type):
                additional_feedback = feedback_type != StopFeedback
                feedback_txt, success = feedback_process(action, feedback)
                self._display_feedback(
                    "\n" + feedback_txt,
                    additional_feedback=additional_feedback,
                    color=Fore.GREEN if success else Fore.RED,
                )
                return

        raise NotImplementedError(f"Feedback {type(feedback)} is not implemented.")

    def _remember_reset(
        self, action: ResetAction, feedback: ResetFeedback
    ) -> tuple[str, bool]:
        self._problem = feedback.problem
        feedback_str = f"\nStarting problem {self._problem.url}:"
        feedback_str += "\n" + "=" * (len(feedback_str) - 2) + "\n"

        feedback_str += "\n  Initial statements:\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)

        return feedback_str, True

    def _remember_stop(
        self, action: StopAction, feedback: StopFeedback
    ) -> tuple[str, bool]:
        if feedback.success:
            return "Congratulations ! You have solved the problem !\n", True
        return "You did not solve the problem.\n", False

    def _remember_match(
        self, action: MatchAction, feedback: MatchFeedback
    ) -> tuple[str, bool]:
        matched_theorem = feedback.theorem
        theorem_str = f"[{matched_theorem.rule_name}] ({matched_theorem})"
        if not feedback.mappings:
            return f"No match found for theorem {theorem_str}:\n", False

        feedback_str = f"Matched theorem {theorem_str}:\n"
        for mapping in feedback.mappings:
            mapping_str = theorem_mapping_str(matched_theorem, mapping)
            if mapping_str in self._known_mappings:
                continue
            self._mappings[mapping_str] = (matched_theorem, mapping)
            self._known_mappings.add(mapping_str)
            feedback_str += f"  - [{mapping_str}]\n"
        return feedback_str, True

    def _remember_apply_theorem(
        self, action: ApplyTheoremAction, feedback: ApplyTheoremFeedback
    ) -> tuple[str, bool]:
        theorem = action.theorem
        rname = theorem.rule_name
        if not feedback.success:
            return f"Failed to apply theorem [{rname}] ({theorem})\n", False

        feedback_str = f"Successfully applied theorem [{rname}] ({theorem}):\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)
        if not feedback.added and not feedback.to_cache:
            feedback_str += "But no statements were added nor cached ...\n"
        return feedback_str, True

    def _remember_derivations(
        self, action: DeriveAlgebraAction, feedback: DeriveFeedback
    ) -> tuple[str, bool]:
        new_mappings: list[tuple[str, tuple[Point, ...]]] = []
        for predicate, derivations_and_dependencies in feedback.derives.items():
            for derivation_and_dependency in derivations_and_dependencies:
                new_mappings.append((predicate, derivation_and_dependency))
        for predicate, derivations_and_dependencies in feedback.eq4s.items():
            for derivation_and_dependency in derivations_and_dependencies:
                new_mappings.append((predicate, derivation_and_dependency))

        if not new_mappings:
            return "No new derviation found.\n", False

        feedback_str = "New derivations:\n"
        for predicate, derivation_and_dependency in new_mappings:
            derived_statement, dependency = derivation_and_dependency
            if derived_statement in self._known_derivations:
                continue
            self._derivations[str(derived_statement)] = (derived_statement, dependency)
            self._known_derivations.add(derived_statement)
            feedback_str += f"  - [{derived_statement}]\n"
        return feedback_str, True

    def _remember_apply_derivation(
        self, action: ApplyDerivationAction, feedback: ApplyDerivationFeedback
    ) -> tuple[str, bool]:
        success = True
        feedback_str = f"Successfully applied derivation [{action.statement}]:\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)
        if not feedback.added and not feedback.to_cache:
            feedback_str += "But no statements were added nor cached ...\n"
            success = False
        return feedback_str, success

    def _remember_aux(self, action: AuxAction, feedback: AuxFeedback):
        success = feedback.success

        aux_str = action.aux_string
        if not success:
            return (
                f"Failed to add auxiliary construction  [{aux_str}]\n"
                "Check that the format is correct "
                "and that the construction is possible.\n",
                False,
            )

        feedback_str = f"Successfully added auxiliary construction [{aux_str}]:\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)
        if not feedback.added and not feedback.to_cache:
            feedback_str += "But no statements were added nor cached ...\n"
            success = False
        return feedback_str, success

    def _list_added_statements(self, added: list[Dependency]) -> str:
        feedback_str = "    Added statements:\n"
        for dep in added:
            feedback_str += f"    - {dep.statement}\n"
            self._all_added.append(dep.statement)
        return feedback_str

    def _list_cached_statements(self, to_cache: list[ToCache]) -> str:
        feedback_str = "    Cached statements:\n"
        for cached in to_cache:
            cached_statement, _deps = cached
            self._all_cached.append(cached_statement)
            feedback_str += f"    - {cached_statement}"
            if str(cached_statement) != str(_deps):
                feedback_str += f" ({_deps})"
            feedback_str += "\n"
        return feedback_str

    def _choose_action_type(self):
        availables_action_types = self.INPUT_TO_ACTION_TYPE.copy()
        for action_input, action_type in self.INPUT_TO_ACTION_TYPE.items():
            if action_type == ApplyTheoremAction and not self._mappings:
                availables_action_types.pop(action_input)
            if action_type == ApplyDerivationAction and not self._derivations:
                availables_action_types.pop(action_input)

        choose_action_type_str = "\nChoose an action type:\n"
        for action_input, action_type in availables_action_types.items():
            action_description = self.ACTION_TYPE_DESCRIPTION[action_type]
            choose_action_type_str += f" -  [{action_input}]: {action_description}\n"
        choose_action_type_str += "Your choice: "
        return self._ask_for_key(availables_action_types, choose_action_type_str)

    def _ask_for_key(
        self,
        dict_to_ask: dict[str, T],
        input_txt: str,
        not_found_txt: str = "Invalid input, try again.\n",
        pop: int = False,
    ) -> T:
        choosen_value = None
        while choosen_value is None:
            if not dict_to_ask:
                raise ValueError("No value to ask for.")
            choosen_input = self._ask_input(input_txt)
            if pop:
                choosen = dict_to_ask.pop(choosen_input, None)
            else:
                choosen = dict_to_ask.get(choosen_input, None)
            if choosen is not None:
                choosen_value = choosen
            else:
                self._display_feedback(
                    not_found_txt, color=Fore.RED, additional_feedback=True
                )
        return choosen_value

    def _display_feedback(
        self,
        feedback: str,
        additional_feedback: bool = False,
        color: int = Fore.WHITE,
    ):
        if additional_feedback:
            print()
            if self._all_cached:
                print(_list_statements("All cached statements:\n", self._all_cached))
            if self._all_added:
                print(_list_statements("All added statements:\n", self._all_added))

        print(color + feedback + Style.RESET_ALL)
        print("-" * 50)

        if not additional_feedback or self._problem is None:
            return

        print(_pretty_problem(self._problem))

    def _ask_input(self, input_txt: str) -> str:
        return input(input_txt).lower().strip()

    def _show_figure(self, proof: "Proof", block: bool = False):
        equal_angles = {}
        for eqangle in self._all_cached:
            if eqangle.predicate != Predicate.EQANGLE:
                continue
            hashed_eqangle = eqangle.hash_tuple
            if hashed_eqangle not in equal_angles:
                equal_angles[hashed_eqangle] = eqangle.args
        proof.symbols_graph.draw_figure(
            equal_angles=list(equal_angles.values()), block=block
        )


def _pretty_problem(problem: "Problem"):
    problem_initial_txt = str(problem).replace("; ", "\n").split(" ? ")[0]
    return (
        Fore.BLUE
        + f"Problem:\n{problem_initial_txt}\n"
        + Style.RESET_ALL
        + "\n"
        + Fore.YELLOW
        + f"Current goal:\n{problem.goal}"
        + Style.RESET_ALL
    )


def _list_statements(
    heading: str, statements: list[Statement], indent: str = ""
) -> str:
    feedback_str = heading
    for statement in statements:
        feedback_str += indent + f"- {statement}\n"
    return feedback_str
