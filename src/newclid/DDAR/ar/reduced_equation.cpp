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
    do
    {
        changed = false;
        for (const auto &[term, eq_ptr] : _system->solved_variables())
        {
            const Equation &eq = *eq_ptr;
            changed |= substitute_variable(term, eq);
        }
    } while (changed);

    while (!_remainder.empty())
    {
        const Term &head = *_remainder.begin();

        auto it = _system->solved_terms().find(head);

        if (it == _system->solved_terms().end())
        {
            break;
        }

        const Equation &substitute_eq = *it->second;
        _remainder -= substitute_eq * head.coeff();
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
    bool flag = true;
    Equation new_equation = _remainder;
    while (flag)
    {
        flag = false;
        for (auto &term : new_equation.terms())
        {
            if (term.contain(var))
            {
                new_equation -= e * (term / var);
                changed = true;
                flag = true;
                break;
            }
        }
        new_equation.reduction();
    }
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