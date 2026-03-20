#ifndef LINEAR_SYSTEM_HPP
#define LINEAR_SYSTEM_HPP

#include <vector>
#include <set>
#include <unordered_map>
#include <map>
#include "ar/equation.hpp"
#include "typedef.hpp"

class Proof;

class ReducedEquation;

class LinearSystem final
{
private:
    std::vector<std::pair<Equation, Proof *>> _equations;
    std::unordered_map<Term, Equation> _solved_variables;
    std::unordered_map<Term, Equation> _solved_terms;
    std::map<Term, std::set<Term>> _pivot_by_next;

public:
    LinearSystem() = default;

    void reduce_next(Equation &e);

    void add_reduced_equation(Proof *pf);

    void print_equations() const;

    const Equation &at(size_t index) const;

    const std::pair<Equation, Proof *> &pair_at(size_t index) const;

    size_t size() const;

    const std::unordered_map<Term, Equation> &solved_variables() const
    {
        return _solved_variables;
    }

    const std::unordered_map<Term, Equation> &solved_terms() const
    {
        return _solved_terms;
    }

    const std::map<Term, std::set<Term>> &pivot_by_next()
    {
        return _pivot_by_next;
    }
};

#endif // LINEAR_SYSTEM_HPP