from typing import TypeVar
from geosolver.agent.interface import (
    Action,
    ApplyDerivationAction,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    DeductiveAgent,
    Feedback,
    Mapping,
    MatchAction,
    MatchFeedback,
    StopAction,
)
from geosolver.problem import Theorem
from geosolver.proof import Proof, theorem_mapping_str

T = TypeVar("T")


class HumanAgent(DeductiveAgent):
    INPUT_TO_ACTION_TYPE = {
        "match": MatchAction,
        "apply": ApplyTheoremAction,
        "stop": StopAction,
    }
    ACTION_TYPE_DESCRIPTION = {
        MatchAction: "Match a theorem to know on which mappings it can be applied.",
        StopAction: "Stop the proof",
        ApplyTheoremAction: "Apply a theorem on a mapping of points.",
    }

    def __init__(self) -> None:
        super().__init__()
        self._mappings: dict[str, tuple[Theorem, Mapping]] = {}
        self.level = 0

    def act(self, proof: Proof, theorems: list[Theorem]) -> Action:
        choosen_action_type = self._choose_action_type()

        ACTION_TYPE_ACT = {
            StopAction: self._act_stop,
            MatchAction: self._act_match,
            ApplyTheoremAction: self._act_apply_theorem,
        }

        act_method = ACTION_TYPE_ACT[choosen_action_type]
        action = act_method(proof, theorems)
        if isinstance(action, (ApplyTheoremAction, ApplyDerivationAction)):
            self.level += 1
        return action

    def _act_stop(self, proof: Proof, theorems: list[Theorem]) -> Action:
        return StopAction()

    def _act_match(self, proof: Proof, theorems: list[Theorem]) -> Action:
        choose_theorem_str = "\nChoose a theorem: \n"
        for th in theorems:
            choose_theorem_str += f" - [{th.rule_name}]: {th.txt()}\n"
        choose_theorem_str += (
            "Theorem you want to match (type only the name within brackets): "
        )
        theorem_dict = {th.rule_name: th for th in theorems}
        theorem = self._ask_for_key(theorem_dict, choose_theorem_str)
        return MatchAction(theorem, level=self.level)

    def _act_apply_theorem(self, proof: Proof, theorems: list[Theorem]) -> Action:
        choosen_mapping_str = "\nAvailable theorems mappings: \n"
        for mapping_str in self._mappings.keys():
            choosen_mapping_str += f" - [{mapping_str}]\n"
        choosen_mapping_str += "Mapping you want to apply: "

        theorem, mapping = self._ask_for_key(self._mappings, choosen_mapping_str)
        return ApplyTheoremAction(theorem, mapping)

    def remember_effects(self, action: Action, feedback: Feedback):
        feedback_str = ""

        if isinstance(feedback, MatchFeedback):
            matched_theorem = feedback.theorem
            if not feedback.mappings:
                self._display_feedback(
                    "No match found for theorem "
                    f"[{matched_theorem.rule_name}] ({matched_theorem.txt()}):"
                )
                return

            feedback_str = (
                "Matched theorem "
                f"[{matched_theorem.rule_name}] ({matched_theorem.txt()}):"
            )
            for mapping in feedback.mappings:
                mapping_str = theorem_mapping_str(matched_theorem, mapping)
                self._mappings[mapping_str] = (matched_theorem, mapping)
                feedback_str += f"  - {mapping_str}"

        elif isinstance(feedback, ApplyTheoremFeedback):
            theorem = action.theorem
            rname = theorem.rule_name
            if feedback.success:
                feedback_str = (
                    f"Successfully applied theorem [{rname}] ({theorem.txt()}):\n"
                )
                feedback_str += "    Added statements:\n"
                for added in feedback.added:
                    feedback_str += f"     - {str(added)}\n"
                feedback_str += "    Cached statements:\n"
                for cached in feedback.to_cache:
                    name, args, _deps = cached
                    args_names = "".join(arg.name for arg in args)
                    feedback_str += f"     - {name} {args_names}\n"
            else:
                feedback_str = f"Failed to apply theorem [{rname}] ({theorem.txt()})"

        if feedback_str:
            self._display_feedback(feedback_str)

    def _choose_action_type(self):
        choose_action_type_str = "\nChoose an action type:\n"
        for action_input, action_type in self.INPUT_TO_ACTION_TYPE.items():
            action_description = self.ACTION_TYPE_DESCRIPTION[action_type]
            choose_action_type_str += f" -  [{action_input}]: {action_description}\n"
        choose_action_type_str += "Your choice: "
        return self._ask_for_key(self.INPUT_TO_ACTION_TYPE, choose_action_type_str)

    def _ask_for_key(
        self,
        dict_to_ask: dict[str, T],
        input_txt: str,
        not_found_txt: str = "Invalid input, try again.",
    ) -> T:
        choosen_value = None
        while choosen_value is None:
            choosen_input = self._ask_input(input_txt)
            choosen = dict_to_ask.get(choosen_input, None)
            if choosen is not None:
                choosen_value = choosen
            else:
                self._display_feedback(not_found_txt)
        return choosen_value

    def _display_feedback(self, feedback: str):
        print(feedback)

    def _ask_input(self, input_txt: str) -> str:
        return input(input_txt).lower().strip()
