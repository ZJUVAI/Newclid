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
      _eqn(_solver->insert_equation(_statement)),
      _dep(nullptr)
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
    if (_statement->trivial())
    {
        set_proved(ProofState::PROVED_TRIVIAL);
        return;
    }
}

void Proof::ar()
{
    if (_state != ProofState::NOT_PROVED)
    {
        return;
    }

    for (const auto &req : _eqn)
    {
        req->reduce();
        if (req->is_solved())
        {
            _dep = req;
            set_proved(ProofState::PROVED_AR);
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

void Proof::print_equations() const
{
    cout << "Proof Equations for statement: " << _statement->to_string() << endl;
    for (const auto &eq : _eqn)
    {
        cout << "Original Equation: " << eq->original_equation() << endl;
        cout << "Reduced Equation: " << eq->remainder() << endl;
    }
}

vector<Proof *> Proof::get_dependencies() const
{
    switch (_state)
    {
    case ProofState::PROVED_BY_ASSUMPTION:
    case ProofState::PROVED_NUMERICALLY:
    case ProofState::PROVED_TRIVIAL:
    case ProofState::NOT_PROVED:
        return {};
    case ProofState::PROVED_BY_THEOREM:
        return _solver->applications()[_theoremId].hypotheses();
    case ProofState::PROVED_AR:
        vector<Proof *> deps = _dep->statement_dependencies();
        return deps;
    }
    return {};
}

string Proof::reason() const
{
    switch (_state)
    {
    case ProofState::NOT_PROVED:
        return "Not Proved";
    case ProofState::PROVED_BY_ASSUMPTION:
        return "Premise";
    case ProofState::PROVED_NUMERICALLY:
        return "Numerical Check";
    case ProofState::PROVED_TRIVIAL:
        return "Trivial";
    case ProofState::PROVED_BY_THEOREM:
        return _solver->applications()[_theoremId].theorem().rule();
    case ProofState::PROVED_AR:
        return "AR";
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

    for (const auto req : _eqn)
    {
        req->reduce();
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