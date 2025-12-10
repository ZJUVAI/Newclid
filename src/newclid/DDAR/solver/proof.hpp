#ifndef PROOF_HPP
#define PROOF_HPP

#include "predicate/statement.hpp"
#include "solver/ddar.hpp"
#include "type/rational.hpp"
#include "ar/reduced_equation.hpp"

#include <set>
#include <optional>
#include <type_traits>

enum class ProofState : uint8_t
{
    NOT_PROVED,
    PROVED_BY_ASSUMPTION,
    PROVED_NUMERICALLY,
    PROVED_TRIVIAL,
    PROVED_AR,
    PROVED_BY_THEOREM,
};

class Proof
{
public:
    Proof(DDARSolver *solver, std::unique_ptr<Statement> &&p);

    void prove_by_assumption();

    bool is_proved() const { return _state != ProofState::NOT_PROVED; }

    ProofState state() const { return _state; }

    void ar();

    void initial();

    const std::unique_ptr<Statement> &statement() const;

    std::vector<Proof *> get_dependencies() const;

    const std::set<Point> &point_dependencies() const
    {
        return _point_dependencies;
    }

    std::string reason() const;

    void set_theorem(size_t index);

    bool needs_aux() const;

    void set_proved(ProofState state);

    void print_equations() const;

    const size_t &theorem() { return _theoremId; }

    const DDARSolver *solver() const { return _solver; }

    std::vector<ReducedEquation *> reduced_equations() const
    {
        return _eqn;
    }

private:
    DDARSolver *_solver;
    std::unique_ptr<Statement> _statement;
    size_t _theoremId;
    ProofState _state{ProofState::NOT_PROVED};
    std::set<Point> _point_dependencies;
    std::vector<ReducedEquation *> _eqn;
    ReducedEquation *_dep;
};

#endif // PROOF_HPP