#include "ar/linear_combination.hpp"
#include "ar/equation_index.hpp"
#include "ar/equation.hpp"
#include "type/rational.hpp"
#include "type/dist.hpp"
#include <vector>
#include <iostream>

using namespace std;

template <typename VarT>
LinearCombination<VarT>::LinearCombination(const VarType &var, const Rational &coeff)
{
    if (coeff != Rational((long long)0))
    {
        _terms.push_back(TermType(var, coeff));
    }
}

template <typename VarT>
LinearCombination<VarT>::LinearCombination(const VarType &var)
    : LinearCombination(var, 1) {}

template class LinearCombination<Slope>;
template class LinearCombination<DistLog>;
template class LinearCombination<Product>;

template class LinearCombination<EquationIndex<Slope>>;
template class LinearCombination<EquationIndex<DistLog>>;
template class LinearCombination<EquationIndex<Product>>;

template <typename VarT>
int LinearCombination<VarT>::common_denominator() const
{
    int res = 1;
    for (const auto &[var, coeff] : _terms)
    {
        int den = coeff.denominator();
        int g = gcd(res, den);
        res = (res / g) * den;
    }

    return res;
}

template <typename VarT>
LinearCombination<VarT> &LinearCombination<VarT>::operator+=(const LinearCombination<VarT> &other)
{
    *this = *this + other;
    return *this;
}

template <typename VarT>
LinearCombination<VarT> LinearCombination<VarT>::operator+(const LinearCombination<VarT> &rhs) const
{
    LinearCombination<VarT> result;

    auto it1 = begin(), end1 = end();
    auto it2 = rhs.begin(), end2 = rhs.end();

    while (it1 != end1 || it2 != end2)
    {
        if (it1 != end1 && it2 != end2)
        {
            if (it1->first < it2->first)
            {
                result._terms.emplace_back(it1->first, it1->second);
                ++it1;
            }
            else if (it2->first < it1->first)
            {
                result._terms.emplace_back(it2->first, it2->second);
                ++it2;
            }
            else
            {
                Rational coeff = it1->second + it2->second;
                if (coeff != 0)
                {
                    result._terms.emplace_back(it1->first, coeff);
                }
                ++it1;
                ++it2;
            }
        }
        else if (it1 != end1)
        {
            result._terms.emplace_back(it1->first, it1->second);
            ++it1;
        }
        else
        {
            result._terms.emplace_back(it2->first, it2->second);
            ++it2;
        }
    }

    return result;
}

template <typename VarT>
LinearCombination<VarT> &LinearCombination<VarT>::operator-=(const LinearCombination<VarT> &other)
{
    *this = *this - other;
    return *this;
}

template <typename VarT>
LinearCombination<VarT> LinearCombination<VarT>::operator-(const LinearCombination<VarT> &rhs) const
{
    LinearCombination<VarT> result;

    auto it1 = begin(), end1 = end();
    auto it2 = rhs.begin(), end2 = rhs.end();

    while (it1 != end1 || it2 != end2)
    {
        if (it1 != end1 && it2 != end2)
        {
            if (it1->first < it2->first)
            {
                result._terms.emplace_back(it1->first, it1->second);
                ++it1;
            }
            else if (it2->first < it1->first)
            {
                result._terms.emplace_back(it2->first, -it2->second);
                ++it2;
            }
            else
            {
                Rational coeff = it1->second - it2->second;
                if (coeff != 0)
                {
                    result._terms.emplace_back(it1->first, coeff);
                }
                ++it1;
                ++it2;
            }
        }
        else if (it1 != end1)
        {
            result._terms.emplace_back(it1->first, it1->second);
            ++it1;
        }
        else
        {
            result._terms.emplace_back(it2->first, -it2->second);
            ++it2;
        }
    }

    return result;
}

template <typename VarT>
LinearCombination<VarT> &LinearCombination<VarT>::operator*=(const Rational &multiplier)
{
    *this = *this * multiplier;
    return *this;
}

template <typename VarT>
LinearCombination<VarT> LinearCombination<VarT>::operator*(const Rational &multiplier) const
{
    if (multiplier == 0)
    {
        return LinearCombination<VarT>();
    }

    LinearCombination<VarT> result;

    for (const auto &[var, coeff] : _terms)
    {
        result._terms.emplace_back(var, coeff * multiplier);
    }

    return result;
}

template <typename VarT>
LinearCombination<VarT> operator*(const Rational &multiplier, const LinearCombination<VarT> &lc)
{
    return lc * multiplier;
}

template <typename VarT>
LinearCombination<VarT> LinearCombination<VarT>::operator-() const
{
    LinearCombination<VarT> result;

    result._terms.reserve(_terms.size());

    for (const auto &[var, coeff] : _terms)
    {
        result._terms.emplace_back(var, -coeff);
    }

    return *this;
}

template <typename VarT>
bool LinearCombination<VarT>::empty() const
{
    return _terms.empty();
}

template <typename VarT>
typename LinearCombination<VarT>::TermsVectorType::const_iterator LinearCombination<VarT>::begin() const
{
    return _terms.begin();
}

template <typename VarT>
typename LinearCombination<VarT>::TermsVectorType::const_iterator LinearCombination<VarT>::end() const
{
    return _terms.end();
}

template <typename VarT>
const typename LinearCombination<VarT>::TermsVectorType &LinearCombination<VarT>::terms() const
{
    return _terms;
}

template <typename VarT>
typename LinearCombination<VarT>::EvaluationType LinearCombination<VarT>::evaluate() const
{
    EvaluationType sum = EvaluationType();
    for (const auto &[var, coeff] : _terms)
    {
        sum += EquationTraits<VarT>::eval_term(coeff, var);
    }
    return sum;
}

template <typename VarT>
LinearCombination<VarT> LinearCombination<VarT>::linear_combine(
    const Rational &coeff_this,
    const Rational &coeff_other,
    const LinearCombination<VarT> &other)
{
    if (coeff_this == 0)
    {
        return coeff_other * other;
    }
    if (coeff_other == 0)
    {
        return coeff_this * *this;
    }
    return coeff_this * *this + coeff_other * other;
}