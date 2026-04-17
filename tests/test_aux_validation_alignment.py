import pytest

from newclid.generation.worker import ProblemWorker


@pytest.mark.slow
@pytest.mark.parametrize("seed", [198, 582])
def test_aux_only_regressions_filter_known_false_positives(seed):
    args = (
        0,
        seed,
        5,
        500,
        0,
        2,
        True,
        2,
        True,
        False,
        None,
        None,
    )
    data_list, summary = ProblemWorker._process_single_problem(args)

    assert summary.get("fl_statement")
    assert data_list == []
