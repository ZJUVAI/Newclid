#include "ar/linear_system.hpp"

#include <vector>
#include <set>
#include <cassert>
#include <iostream>
#include "solver/proof.hpp"
#include "ar/equation.hpp"
#include "ar/equation_index.hpp"
#include "ar/linear_combination.hpp"

using namespace std;

template <typename VarT>
void LinearSystem<VarT>::reduce_next(LinearCombinationType &e)
{
    while (true)
    {
        const auto &it_begin = e.rhs().lhs().begin();
        const auto &it_next = next(it_begin);

        VarT head = it_begin->first;

        if (it_next == e.rhs().lhs().end())
        {
            _found_variables.insert(head);
            break;
        }

        auto [next_var, next_coeff] = *it_next;

        const auto &echelon_it = _echelon_form.find(next_var);

        if (echelon_it == _echelon_form.end())
        {
            _pivot_by_next[next_var].insert(head);
            break;
        }

        e -= echelon_it->second * next_coeff;
    }
}

template <typename VarT>
void LinearSystem<VarT>::add_reduced_equation(Proof *pf)
{
    auto eq = pf->reduced_equation<VarT>();
    if (!eq)
    {
        return;
    }

    if (eq->is_solved())
    {
        return;
    }

    IndexType const n(_equations.size(), this);
    _equations.push_back(make_pair(eq->original_equation(), pf));

    LinearCombinationType lc(LinearCombination<IndexType>(n), eq->original_equation());

    lc -= eq->linear_combination();

    assert(lc.rhs() == eq->remainder());
    assert(!lc.rhs().lhs().empty());

    auto [v, c] = *(lc.rhs().lhs().begin());

    assert(!_echelon_form.contains(v));

    lc *= Rational(1) / c;
    reduce_next(lc);
    if (!_echelon_form.insert(make_pair(v, lc)).second)
    {
        throw runtime_error("Trying to insert a non-reduced equation");
    }

    auto it = _pivot_by_next.find(v);
    if (it != _pivot_by_next.end())
    {
        for (const auto &pivot : it->second)
        {
            auto it_pivot = _echelon_form.find(pivot);
            reduce_next(it_pivot->second);
        }
        _pivot_by_next.erase(it);
    }
}

template <typename VarT>
const pair<typename LinearSystem<VarT>::EquationType, Proof *> &LinearSystem<VarT>::pair_at(IndexType index) const
{
    size_t i = index.index();
    if (i >= _equations.size())
    {
        throw runtime_error("Index out of range");
    }
    return _equations[i];
}

template <typename VarT>
const typename LinearSystem<VarT>::EquationType &LinearSystem<VarT>::at(IndexType index) const
{
    return pair_at(index).first;
}

template <typename VarT>
size_t LinearSystem<VarT>::size() const
{
    return _equations.size();
}

template <typename VarT>
set<VarT> LinearSystem<VarT>::new_found_variables() const
{
    return _found_variables;
}

template <typename VarT>
void LinearSystem<VarT>::clear_new_found_variables()
{
    _found_variables.clear();
}

template class LinearSystem<Dist>;
template class LinearSystem<Slope>;
template class LinearSystem<DistLog>;