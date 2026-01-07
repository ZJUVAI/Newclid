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

        const Equation *eq_var = get_solved_variable(*it_next);
        const Equation *eq_term = get_solved_term(*it_next);

        if (!eq_var && !eq_term)
        {
            _pivot_by_next[*it_next].insert(head);
            break;
        }
        if (eq_term)
        {
            e -= *eq_term * it_next->coeff();
        }
        else if (eq_var)
        {
            e -= *eq_var * it_next->coeff();
        }
    }
    return;
}

void LinearSystem::update()
{
    _solved_variables.clear();
    _solved_terms.clear();
    _pivot_by_next.clear();

    for (const auto &[original_eq, pf] : _equations)
    {
        Equation e = original_eq;
        e.normalize();

        if (e.empty())
        {
            continue;
        }

        ReducedEquation req(e, this);
        req.reduce();
        e = req.remainder();

        if (e.empty())
        {
            continue;
        }

        Term head = *e.begin();
        bool is_linear = e.linear();

        auto ptr = std::make_unique<Equation>(std::move(e));
        bool inserted = false;
        if (is_linear)
        {
            inserted = _solved_variables.emplace(head, std::move(ptr)).second;
        }
        else
        {
            inserted = _solved_terms.emplace(head, std::move(ptr)).second;
        }

        if (!inserted)
        {
            throw std::runtime_error("Trying to insert a duplicate solved equation during update");
        }

        auto pivot_it = _pivot_by_next.find(head);
        if (pivot_it != _pivot_by_next.end())
        {

            for (const Term &waiting_pivot : pivot_it->second)
            {

                auto var_it = _solved_variables.find(waiting_pivot);
                if (var_it != _solved_variables.end())
                {
                    reduce_next(*var_it->second);
                }

                auto term_it = _solved_terms.find(waiting_pivot);
                if (term_it != _solved_terms.end())
                {
                    reduce_next(*term_it->second);
                }
            }
            _pivot_by_next.erase(pivot_it);
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
        cout << var << " : " << *eqn << endl;
    }
    cout << endl;
    cout << "Solved Terms:" << endl;
    for (const auto &[term, eqn] : _solved_terms)
    {
        cout << term << " : " << *eqn << endl;
    }
}

void LinearSystem::add_reduced_equation(Proof *pf, string type)
{
    auto eqs = pf->reduced_equations(type);
    for (auto &eq : eqs)
    {
        eq->reduce();
        if (eq->is_solved())
        {
            continue;
        }

        EquationIndex const n(_equations.size(), this);
        _equations.emplace_back(eq->original_equation(), pf);

        Equation e = eq->remainder();
        e.set_index(n.index(), this);

        Term head = *e.begin();
        e *= Rational(1) / head.coeff();
        reduce_next(e);

        bool is_linear = e.linear();
        head = *e.begin();

        bool success = false;
        auto ptr = std::make_unique<Equation>(std::move(e));

        if (is_linear)
        {
            success = _solved_variables.emplace(head, std::move(ptr)).second;
        }
        else
        {
            success = _solved_terms.emplace(head, std::move(ptr)).second;
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
                auto it_var = _solved_variables.find(pivot);
                if (it_var != _solved_variables.end())
                {
                    reduce_next(*it_var->second);
                }

                auto it_term = _solved_terms.find(pivot);
                if (it_term != _solved_terms.end())
                {
                    reduce_next(*it_term->second);
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