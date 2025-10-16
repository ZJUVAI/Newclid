#include "solver/proof.hpp"
#include "predicate/statement.hpp"
#include "solver/ddar.hpp"
#include "type/dist.hpp"
#include "type/slope.hpp"
#include "type/distlog.hpp"
#include <set>
#include <vector>
#include <optional>
#include <cassert>

using namespace std;

Proof::Proof(DDARSolver *solver, std::unique_ptr<Statement> &&p)
    : _solver(solver),
      _statement(move(p)),
      _dist_eqn(_solver->insert_equation<Dist>(_statement)),
      _slope_eqn(_solver->insert_equation<Slope>(_statement)),
      _distlog_eqn(_solver->insert_equation<DistLog>(_statement))
{
}

void Proof::prove_by_assumption()
{
    set_proved(ProofState::PROVED_BY_ASSUMPTION);
}

void Proof::initial()
{
    if (_statement->numerical_only())
    {
        if (_statement->check_numerically())
        {
            set_proved(ProofState::PROVED_NUMERICALLY);
            return;
        }
        throw runtime_error("尝试添加错误的仅数值检验命题");
    }
}

void Proof::ar()
{
    if (_state != ProofState::NOT_PROVED)
    {
        return;
    }

    if (_dist_eqn.second != nullptr)
    {
        _dist_eqn.second->reduce();
        if (_dist_eqn.second->is_solved())
        {
            set_proved(ProofState::PROVED_AR_DIST);
            return;
        }
    }

    if (_slope_eqn.second != nullptr)
    {
        _slope_eqn.second->reduce();
        if (_slope_eqn.second->is_solved())
        {
            set_proved(ProofState::PROVED_AR_SLOPE);
            return;
        }
    }

    if (_distlog_eqn.second != nullptr)
    {
        _distlog_eqn.second->reduce();
        if (_distlog_eqn.second->is_solved())
        {
            set_proved(ProofState::PROVED_AR_DISTLOG);
            return;
        }
    }

    return;
}

void Proof::set_theorem(size_t index)
{
    _theoremId = index;
    set_proved(ProofState::PROVED_BY_THEOREM);
}

const unique_ptr<Statement> &Proof::statement() const
{
    return _statement;
}

vector<Proof *> Proof::get_dependencies() const
{
    switch (_state)
    {
    case ProofState::PROVED_BY_ASSUMPTION:
    case ProofState::PROVED_NUMERICALLY:
    case ProofState::NOT_PROVED:
        return {};
    case ProofState::PROVED_BY_THEOREM:
        return _solver->applications()[_theoremId].hypotheses();
    case ProofState::PROVED_AR_DIST:
        return _dist_eqn.second->statement_dependencies();
    case ProofState::PROVED_AR_SLOPE:
        return _slope_eqn.second->statement_dependencies();
    case ProofState::PROVED_AR_DISTLOG:
        return _distlog_eqn.second->statement_dependencies();
    }
    return {};
}

string Proof::reason() const
{
    switch (_state)
    {
    case ProofState::NOT_PROVED:
        return "未证明";
    case ProofState::PROVED_BY_ASSUMPTION:
        return "Assumption";
    case ProofState::PROVED_NUMERICALLY:
        return "Numerical Check";
    case ProofState::PROVED_BY_THEOREM:
        return _solver->applications()[_theoremId].theorem().name();
    case ProofState::PROVED_AR_DIST:
        return "ar for Dist";
    case ProofState::PROVED_AR_SLOPE:
        return "ar for Slope";
    case ProofState::PROVED_AR_DISTLOG:
        return "ar for DistLog";
    default:
        return "Unknown";
    }
}

bool Proof::needs_aux() const
{
    assert(_state != ProofState::NOT_PROVED);
    const auto max_pt = *std::max_element(_statement->points().begin(), _statement->points().end());
    return std::any_of(_point_dependencies.begin(), _point_dependencies.end(),
                       [&max_pt](const Point &pt)
                       {
                           return pt > max_pt;
                       });
}

void Proof::set_proved(ProofState state)
{
    if (state == ProofState::NOT_PROVED)
    {
        return;
    }

    if (_state != ProofState::NOT_PROVED)
    {
        throw runtime_error("Proof already proved");
    }

    _state = state;
    _solver->push_established_statement(this);

    assert(_statement->check_numerically());

    if (_dist_eqn.second != nullptr)
    {
        _dist_eqn.second->reduce();
    }

    if (_slope_eqn.second != nullptr)
    {
        _slope_eqn.second->reduce();
    }

    if (_distlog_eqn.second != nullptr)
    {
        _distlog_eqn.second->reduce();
    }

    _solver->add_established_equations(this);

    for (const auto &dep : get_dependencies())
    {
        for (Point const &pt : dep->point_dependencies())
        {
            _point_dependencies.insert(pt);
        }
    }

    for (Point const &pt : _statement->points())
    {
        _point_dependencies.insert(pt);
    }
}