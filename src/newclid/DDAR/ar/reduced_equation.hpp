#ifndef REDUCED_EQUATION_HPP
#define REDUCED_EQUATION_HPP

#include "ar/equation.hpp"
#include "ar/linear_system.hpp"

class ReducedEquation final
{
private:
    Equation _original_equation;
    LinearSystem *_system;
    Equation _remainder;
    size_t _cached_version{0};  // Version when last reduced
    bool _reduction_complete{false};  // Whether reduction is complete

public:
    explicit ReducedEquation(Equation &equation, LinearSystem *system);

    const Equation &original_equation() const { return _original_equation; }

    const LinearSystem *linear_system() const { return _system; }

    const Equation &remainder() const { return _remainder; }

    bool is_solved() const;

    bool substitute_variable(Term var, const Equation &e);

    void reduce();

    void set_index(size_t index, const LinearSystem *system);

    std::vector<Proof *> statement_dependencies() const;
};

#endif // REDUCED_EQUATION_HPP