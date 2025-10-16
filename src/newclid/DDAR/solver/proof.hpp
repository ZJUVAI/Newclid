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
    PROVED_AR_DIST,
    PROVED_AR_SLOPE,
    PROVED_AR_DISTLOG,
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

    const size_t &theorem() { return _theoremId; }

    const DDARSolver *solver() const { return _solver; }

    template <typename VarT>
    const ReducedEquation<VarT> *reduced_equation() const
    {
        if constexpr (std::is_same_v<VarT, Dist>)
        {
            return _dist_eqn.second;
        }
        else if constexpr (std::is_same_v<VarT, Slope>)
        {
            return _slope_eqn.second;
        }
        else if constexpr (std::is_same_v<VarT, DistLog>)
        {
            return _distlog_eqn.second;
        }
        else
        {
            throw std::runtime_error("Invalid variable type");
        }
        return nullptr;
    }

    template <typename VarT>
    const Rational &equation_coeff() const
    {
        if constexpr (std::is_same_v<VarT, Dist>)
        {
            return _dist_eqn.first;
        }
        else if constexpr (std::is_same_v<VarT, Slope>)
        {
            return _slope_eqn.first;
        }
        else if constexpr (std::is_same_v<VarT, DistLog>)
        {
            return _distlog_eqn.first;
        }
        else
        {
            throw std::runtime_error("Invalid variable type");
        }
    }

private:
    DDARSolver *_solver;
    std::unique_ptr<Statement> _statement;
    size_t _theoremId;
    ProofState _state{ProofState::NOT_PROVED};
    std::set<Point> _point_dependencies;
    std::pair<Rational, ReducedEquation<Dist> *> _dist_eqn;
    std::pair<Rational, ReducedEquation<Slope> *> _slope_eqn;
    std::pair<Rational, ReducedEquation<DistLog> *> _distlog_eqn;
};

#endif // PROOF_HPP