from newclid.evaluation.search_runtime import problem_to_dsl
from newclid.configs import default_defs_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX


def _load_defs():
    return DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(default_defs_path()))


def test_problem_dsl_uses_basic_order():
    problem = ProblemJGEX.from_text("a b c = triangle12 a b c ? cong a b a c")
    defs = _load_defs()

    dsl = problem_to_dsl(problem, defs)

    assert (
        dsl
        == "<problem> a : ; b : ; c : rconst a b a c 1/2 [000] ? cong a b a c </problem>"
    )
