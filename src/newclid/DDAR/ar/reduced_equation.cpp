#include "ar/reduced_equation.hpp"

#include "ar/equation.hpp"
#include "ar/linear_system.hpp"

using namespace std;

ReducedEquation::ReducedEquation(Equation &equation, LinearSystem *system) : _original_equation(equation),
                                                                             _system(system),
                                                                             _remainder(equation)
{
}

void ReducedEquation::set_index(size_t index, const LinearSystem *system)
{
    _remainder.set_index(index, const_cast<LinearSystem *>(system));
    // _original_equation.set_index(index, const_cast<LinearSystem *>(system));
}

void ReducedEquation::reduce()
{
    if (_remainder.empty())
    {
        return;
    }

    bool changed = true;
    while (changed)
    {
        changed = false;
        for (const auto &[term, eq] : _system->solved_variables())
        {
            changed |= substitute_variable(term, eq);
        }
    }

    while (!_remainder.empty())
    {
        auto &term = *_remainder.begin();
        auto itr = _system->solved_terms().find(term);
        if (itr != _system->solved_terms().end())
        {
            _remainder -= itr->second * term.coeff();
        }
        else
        {
            break;
        }
    }
    _remainder.reduction();
}

bool ReducedEquation::is_solved() const
{
    return _remainder.empty();
}

bool ReducedEquation::substitute_variable(Term var, const Equation &e)
{
    bool changed = false;
    Equation new_equation = _remainder;
    for (auto &term : _remainder.terms())
    {
        if (term.contain(var))
        {
            new_equation -= e * (term / var);
            changed = true;
        }
    }
    new_equation.reduction();
    _remainder = new_equation;
    return changed;
}

vector<Proof *> ReducedEquation::statement_dependencies() const
{
    std::set<Proof *> res;
    for (const auto &[t, index] : _remainder.combination())
    {
        if (!index.is_valid())
        {
            continue;
        }
        res.insert(_system->pair_at(index.index()).second);
    }
    return vector<Proof *>(res.begin(), res.end());
}