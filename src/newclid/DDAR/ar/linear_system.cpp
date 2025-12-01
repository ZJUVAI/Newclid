#include "ar/linear_system.hpp"

#include <vector>
#include <set>
#include <cassert>
#include <iostream>
#include "solver/proof.hpp"
#include "ar/equation.hpp"
#include "ar/equation_index.hpp"

using namespace std;

void LinearSystem::reduce_next(Equation &e)
{
    e.normalize();
    while (true)
    {
        const auto &it_begin = e.begin();
        const auto &it_next = next(it_begin);

        Term head = *it_begin;

        if (it_next == e.end())
        {
            break;
        }

        const auto &term_it = _solved_terms.find(*it_next);
        const auto &var_it = _solved_variables.find(*it_next);

        if (term_it == _solved_terms.end() && var_it == _solved_variables.end())
        {
            _pivot_by_next[*it_next].insert(head);
            break;
        }

        if (term_it != _solved_terms.end())
        {
            e -= term_it->second * it_next->coeff();
        }
        else
        {
            e -= var_it->second * it_next->coeff();
        }
    }
}

void LinearSystem::print_equations() const
{
    cout << "Linear System Equations:" << endl;
    for (const auto &[eqn, pf] : _equations)
    {
        cout << "Equation: " << eqn << endl;
        cout << "Proved by: " << pf->statement()->to_string() << endl;
    }
    cout << endl;
    cout << "Solved Variables:" << endl;
    for (const auto &[var, eqn] : _solved_variables)
    {
        cout << var << " : " << eqn << endl;
    }
    cout << endl;
    cout << "Solved Terms:" << endl;
    for (const auto &[term, eqn] : _solved_terms)
    {
        cout << term << " : " << eqn << endl;
    }
}

void LinearSystem::add_reduced_equation(Proof *pf)
{
    auto eqs = pf->reduced_equations();

    for (auto &eq : eqs)
    {
        eq->reduce();
        if (eq->is_solved())
        {
            continue;
        }

        EquationIndex const n(_equations.size(), this);
        _equations.push_back(make_pair(eq->original_equation(), pf));

        Equation e = eq->remainder();
        e.set_index(n.index(), this);

        Term head = *e.begin();

        e *= Rational(1) / head.coeff();
        reduce_next(e);

        bool success = false;
        if (e.linear())
        {
            success = _solved_variables.insert(make_pair(*e.begin(), e)).second;
        }
        else
        {
            success = _solved_terms.insert(make_pair(*e.begin(), e)).second;
        }
        if (!success)
        {
            throw runtime_error("Trying to insert a non-reduced equation");
        }

        auto it = _pivot_by_next.find(head);
        if (it != _pivot_by_next.end())
        {
            for (const auto &pivot : it->second)
            {
                auto it_pivot = _solved_variables.find(pivot);
                if (it_pivot != _solved_variables.end())
                {
                    reduce_next(it_pivot->second);
                }
                it_pivot = _solved_terms.find(pivot);
                if (it_pivot != _solved_terms.end())
                {
                    reduce_next(it_pivot->second);
                }
            }
            _pivot_by_next.erase(it);
        }
    }
}

const Equation &LinearSystem::at(size_t index) const
{
    return pair_at(index).first;
}

const std::pair<Equation, Proof *> &LinearSystem::pair_at(size_t index) const
{
    if (index >= _equations.size())
    {
        throw runtime_error("Index out of range");
    }
    return _equations[index];
}

size_t LinearSystem::size() const
{
    return _equations.size();
}