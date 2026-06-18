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

    problem = ProblemJGEX.from_text(
        "x y z i a b c = incenter2 x y z i a b c ? cong x y x y"
    )
    dsl = problem_to_dsl(problem, defs)

    assert (
        dsl
        == "<problem> i : eqangle a b a i a i a c [000] eqangle a c c i c i b c [001] ; "
        "x : coll b c x [002] perp b c i x [003] ; "
        "y : coll a c y [004] perp a c i y [005] ; "
        "z : coll a b z [006] perp a b i z [007] ? cong x y x y </problem>"
    )
