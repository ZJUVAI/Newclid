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
    PROVED_AR_DIST,
    PROVED_AR_SLOPE,
    PROVED_AR_DISTLOG,
    PROVED_BY_THEOREM,
    PROVED_BY_DOUBLEPOINT,
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

    std::string reason() const;

    void set_theorem(size_t index);

    void set_proved(Proof *doublepoint, Proof *original);

    void set_proved(ProofState state);

    void print_equations() const;

    const size_t &theorem() const { return _theoremId; }

    const DDARSolver *solver() const { return _solver; }

    std::string name() const { return _statement->name(); }

    std::vector<ReducedEquation *> reduced_equations(std::string type) const
    {
        if (type == "dist")
        {
            return _eqn_dist;
        }
        if (type == "distlog")
        {
            return _eqn_distlog;
        }
        if (type == "slope")
        {
            return _eqn_slope;
        }
        return {};
    }

private:
    DDARSolver *_solver;
    std::unique_ptr<Statement> _statement;
    size_t _theoremId;
    ProofState _state{ProofState::NOT_PROVED};
    std::vector<ReducedEquation *> _eqn_dist;
    std::vector<ReducedEquation *> _eqn_slope;
    std::vector<ReducedEquation *> _eqn_distlog;
    ReducedEquation *_dep;
    std::vector<Proof *> _deps;
};

#endif // PROOF_HPP