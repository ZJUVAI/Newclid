#ifndef LINEAR_SYSTEM_HPP
#define LINEAR_SYSTEM_HPP

#include <vector>
#include <set>
#include <unordered_map>
#include <memory>
#include "ar/equation.hpp"
#include "typedef.hpp"

class Proof;
class ReducedEquation;

class LinearSystem final
{
private:
    std::vector<std::pair<Equation, Proof *>> _equations;
    std::unordered_map<Term, std::unique_ptr<Equation>> _solved_variables;
    std::unordered_map<Term, std::unique_ptr<Equation>> _solved_terms;
    std::unordered_map<Term, std::set<Term>> _pivot_by_next;
    int _next_id = 0;
    std::map<Term, int> _solved_id;

public:
    LinearSystem() = default;

    void reduce_next(Equation &e);

    void add_reduced_equation(Proof *pf);

    void print_equations() const;

    const Equation &at(size_t index) const;

    const std::pair<Equation, Proof *> &pair_at(size_t index) const;

    size_t size() const;

    const std::unordered_map<Term, std::unique_ptr<Equation>> &solved_variables() const
    {
        return _solved_variables;
    }

    const std::unordered_map<Term, std::unique_ptr<Equation>> &solved_terms() const
    {
        return _solved_terms;
    }

    const Equation *get_solved_variable(const Term &t) const
    {
        auto it = _solved_variables.find(t);
        return it != _solved_variables.end() ? it->second.get() : nullptr;
    }

    const Equation *get_solved_term(const Term &t) const
    {
        auto it = _solved_terms.find(t);
        return it != _solved_terms.end() ? it->second.get() : nullptr;
    }

    const std::unordered_map<Term, std::set<Term>> &pivot_by_next()
    {
        return _pivot_by_next;
    }
};

#endif // LINEAR_SYSTEM_HPP