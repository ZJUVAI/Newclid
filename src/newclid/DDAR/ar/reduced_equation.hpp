#ifndef REDUCED_EQUATION_HPP
#define REDUCED_EQUATION_HPP

#include "ar/equation.hpp"
#include "ar/linear_system.hpp"

template <typename VarT>
class ReducedEquation final
{
public:
    using EquationType = Equation<VarT>;
    using LinearCombinationType = typename LinearSystem<VarT>::LinearCombinationType;
    using VarType = VarT;

private:
    const EquationType _original_equation;
    const LinearSystem<VarT> *_system;
    LinearCombinationType _linear_combination;
    EquationType _remainder;

public:
    explicit ReducedEquation(const EquationType &equation, const LinearSystem<VarT> *system);

    const EquationType &original_equation() const { return _original_equation; }

    const LinearSystem<VarT> *linear_system() const { return _system; }

    const LinearCombinationType &linear_combination() const { return _linear_combination; }

    const EquationType &remainder() const { return _remainder; }

    void reduce();

    bool is_solved() const;

    auto statement_dependencies() const
    {
        std::vector<Proof *> dependencies;
        std::transform(_linear_combination.lhs().begin(), _linear_combination.lhs().end(), std::back_inserter(dependencies),
                       [this](const auto &term)
                       {
                           return _system->pair_at(term.first).second;
                       });
        return dependencies;
    }
};

#endif // REDUCED_EQUATION_HPP