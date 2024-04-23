from typing import TypeVar
from geosolver.agent.interface import (
    Action,
    ApplyDerivationAction,
    ApplyDerivationFeedback,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    DeductiveAgent,
    DeriveAlgebraAction,
    DeriveFeedback,
    Feedback,
    Mapping,
    MatchAction,
    MatchFeedback,
    StopAction,
    StopFeedback,
)
from geosolver.dependencies.dependency import Dependency
from geosolver.geometry import Point
from geosolver.problem import Construction, Theorem, name_and_arguments_to_str
from geosolver.proof import Proof, theorem_mapping_str
from geosolver.statement.adder import ToCache

T = TypeVar("T")


class HumanAgent(DeductiveAgent):
    INPUT_TO_ACTION_TYPE = {
        "match": MatchAction,
        "apply": ApplyTheoremAction,
        "resolve derivations": DeriveAlgebraAction,
        "derive": ApplyDerivationAction,
        "stop": StopAction,
    }
    ACTION_TYPE_DESCRIPTION = {
        MatchAction: "Match a theorem to know on which mappings it can be applied.",
        StopAction: "Stop the proof",
        ApplyTheoremAction: "Apply a theorem on a mapping of points.",
        DeriveAlgebraAction: "Resolve available derivation from current proof state",
        ApplyDerivationAction: "Apply a derivation",
    }

    def __init__(self) -> None:
        super().__init__()
        self._mappings: dict[str, tuple[Theorem, Mapping]] = {}
        self._derivations: dict[str, tuple[str, Mapping]] = {}
        self._all_added: list[Dependency] = []
        self._all_cached: list[Construction] = []
        self.level = 0

    def act(self, proof: Proof, theorems: list[Theorem]) -> Action:
        choosen_action_type = self._choose_action_type()

        ACTION_TYPE_ACT = {
            StopAction: self._act_stop,
            MatchAction: self._act_match,
            ApplyTheoremAction: self._act_apply_theorem,
            DeriveAlgebraAction: self._act_resolve_derivations,
            ApplyDerivationAction: self._act_apply_derivation,
        }

        act_method = ACTION_TYPE_ACT[choosen_action_type]
        action = act_method(theorems)
        if isinstance(action, (ApplyTheoremAction, ApplyDerivationAction)):
            self.level += 1
        return action

    def _act_stop(self, theorems: list[Theorem]) -> Action:
        return StopAction()

    def _act_match(self, theorems: list[Theorem]) -> Action:
        choose_theorem_str = "\nChoose a theorem: \n"
        for th in theorems:
            choose_theorem_str += f" - [{th.rule_name}]: {th.txt()}\n"
        choose_theorem_str += (
            "Theorem you want to match (type only the name within brackets): "
        )
        theorem_dict = {th.rule_name: th for th in theorems}
        theorem = self._ask_for_key(theorem_dict, choose_theorem_str)
        return MatchAction(theorem, level=self.level)

    def _act_apply_theorem(self, theorems: list[Theorem]) -> Action:
        choosen_mapping_str = "\nAvailable theorems mappings: \n"
        for mapping_str in self._mappings.keys():
            choosen_mapping_str += f" - [{mapping_str}]\n"
        choosen_mapping_str += "Mapping you want to apply: "
        theorem, mapping = self._ask_for_key(
            self._mappings, choosen_mapping_str, pop=True
        )
        return ApplyTheoremAction(theorem, mapping)

    def _act_resolve_derivations(self, theorems: list[Theorem]) -> Action:
        return DeriveAlgebraAction(level=self.level)

    def _act_apply_derivation(self, theorems: list[Theorem]) -> Action:
        choosen_mapping_str = "\nAvailable derivations mappings: \n"
        for mapping_str in self._derivations.keys():
            choosen_mapping_str += f" - [{mapping_str}]\n"
        choosen_mapping_str += "Mapping you want to apply: "
        derivation, mapping = self._ask_for_key(
            self._derivations, choosen_mapping_str, pop=True
        )
        return ApplyDerivationAction(derivation, mapping)

    def remember_effects(self, action: Action, feedback: Feedback):
        feedback_type_to_method = {
            StopFeedback: self._remember_stop,
            MatchFeedback: self._remember_match,
            ApplyTheoremFeedback: self._remember_apply_theorem,
            DeriveFeedback: self._remember_derivations,
            ApplyDerivationFeedback: self._remember_apply_derivation,
        }

        for feedback_type, feedback_process in feedback_type_to_method.items():
            if isinstance(feedback, feedback_type):
                self._display_feedback(feedback_process(action, feedback))
                return

        raise NotImplementedError(f"Feedback {type(feedback)} is not implemented.")

    def _remember_stop(self, action: StopAction, feedback: StopFeedback) -> str:
        if feedback.success:
            return "Congratulations ! You have solved the problem !"
        return "You did not solve the problem."

    def _remember_match(self, action: MatchAction, feedback: MatchFeedback) -> str:
        matched_theorem = feedback.theorem
        theorem_str = f"[{matched_theorem.rule_name}] ({matched_theorem.txt()})"
        if not feedback.mappings:
            return f"No match found for theorem {theorem_str}:\n"

        feedback_str = f"Matched theorem {theorem_str}:\n"
        for mapping in feedback.mappings:
            mapping_str = theorem_mapping_str(matched_theorem, mapping)
            self._mappings[mapping_str] = (matched_theorem, mapping)
            feedback_str += f"  - [{mapping_str}]\n"
        return feedback_str

    def _remember_apply_theorem(
        self, action: ApplyTheoremAction, feedback: ApplyTheoremFeedback
    ) -> str:
        theorem = action.theorem
        rname = theorem.rule_name
        if not feedback.success:
            return f"Failed to apply theorem [{rname}] ({theorem.txt()})\n"

        feedback_str = f"Successfully applied theorem [{rname}] ({theorem.txt()}):\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)
        if not feedback.added and not feedback.to_cache:
            feedback_str += "But no statements were added nor cached ...\n"
        return feedback_str

    def _remember_derivations(
        self, action: DeriveAlgebraAction, feedback: DeriveFeedback
    ) -> str:
        new_mappings: list[tuple[str, tuple[Point, ...]]] = []
        for name, mappings in feedback.derives.items():
            for mapping in mappings:
                new_mappings.append((name, mapping))
        for name, mappings in feedback.eq4s.items():
            for mapping in mappings:
                new_mappings.append((name, mapping))

        if not new_mappings:
            return "No new derviation found.\n"

        feedback_str = "New derivations:\n"
        for name, mapping in new_mappings:
            derivation_str = str(Construction(name, mapping[:-1]))
            self._derivations[derivation_str] = (name, mapping)
            feedback_str += f"  - [{derivation_str}]\n"
        return feedback_str

    def _remember_apply_derivation(
        self, action: ApplyDerivationAction, feedback: ApplyDerivationFeedback
    ) -> str:
        derivation_str = name_and_arguments_to_str(
            action.derivation_name, action.derivation_arguments[:-1], " "
        )
        feedback_str = f"Successfully applied derivation [{derivation_str}]:\n"
        if feedback.added:
            feedback_str += self._list_added_statements(feedback.added)
        if feedback.to_cache:
            feedback_str += self._list_cached_statements(feedback.to_cache)
        if not feedback.added and not feedback.to_cache:
            feedback_str += "But no statements were added nor cached ...\n"
        return feedback_str

    def _list_added_statements(self, added: list[Dependency]) -> str:
        feedback_str = "    Added statements:\n"
        for added in added:
            feedback_str += f"    - {added}\n"
            self._all_added.append(added)
        return feedback_str

    def _list_cached_statements(self, to_cache: list[ToCache]) -> str:
        feedback_str = "    Cached statements:\n"
        for cached in to_cache:
            name, args, _deps = cached
            cached_construction = Construction(name, args)
            self._all_cached.append(cached_construction)
            feedback_str += f"    - {cached_construction}"
            if str(cached_construction) != str(_deps):
                feedback_str += f" ({_deps})"
            feedback_str += "\n"
        return feedback_str

    def _choose_action_type(self):
        choose_action_type_str = "\nChoose an action type:\n"
        for action_input, action_type in self.INPUT_TO_ACTION_TYPE.items():
            if action_type == ApplyTheoremAction and not self._mappings:
                continue
            if action_type == ApplyDerivationAction and not self._derivations:
                continue
            action_description = self.ACTION_TYPE_DESCRIPTION[action_type]
            choose_action_type_str += f" -  [{action_input}]: {action_description}\n"
        choose_action_type_str += "Your choice: "
        return self._ask_for_key(self.INPUT_TO_ACTION_TYPE, choose_action_type_str)

    def _ask_for_key(
        self,
        dict_to_ask: dict[str, T],
        input_txt: str,
        not_found_txt: str = "Invalid input, try again.\n",
        pop: int = False,
    ) -> T:
        choosen_value = None
        while choosen_value is None:
            choosen_input = self._ask_input(input_txt)
            if pop:
                choosen = dict_to_ask.pop(choosen_input, None)
            else:
                choosen = dict_to_ask.get(choosen_input, None)
            if choosen is not None:
                choosen_value = choosen
            else:
                self._display_feedback(not_found_txt)
        return choosen_value

    def _display_feedback(self, feedback: str):
        print(feedback)
        if self._all_cached:
            print(_list_constructions("All cached statements:\n", self._all_cached))
        if self._all_added:
            print(_list_constructions("All added statements:\n", self._all_added))

        print("-" * 30)
        print(f"Current goal:\n{self._problem.goal}")

    def _ask_input(self, input_txt: str) -> str:
        return input(input_txt).lower().strip()


def _list_constructions(
    heading: str, constructions: list[Construction], indent: str = ""
) -> str:
    feedback_str = heading
    for construction in constructions:
        feedback_str += indent + f"- {construction}\n"
    return feedback_str
