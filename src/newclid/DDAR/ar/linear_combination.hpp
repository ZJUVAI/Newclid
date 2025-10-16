#ifndef LINEAR_COMBINATION_HPP
#define LINEAR_COMBINATION_HPP

#include <vector>
#include <iostream>
#include "type/rational.hpp"
#include "ar/equation_traits.hpp"

template <typename VarT>
class LinearCombination final
{
public:
    using VarType = VarT;
    using EvaluationType = typename EquationTraits<VarT>::EvaluationType;
    using TermsVectorType = std::vector<std::pair<VarType, Rational>>;
    using TermType = std::pair<VarType, Rational>;

    LinearCombination() = default;

    LinearCombination(const VarType &var, const Rational &coeff);

    explicit LinearCombination(const VarType &var);

    int common_denominator() const;

    LinearCombination &operator+=(const LinearCombination &other);
    LinearCombination operator+(const LinearCombination &other) const;

    LinearCombination &operator-=(const LinearCombination &other);
    LinearCombination operator-(const LinearCombination &other) const;

    LinearCombination &operator*=(const Rational &multiplier);
    LinearCombination operator*(const Rational &multiplier) const;

    LinearCombination operator-() const;

    bool empty() const;

    EvaluationType evaluate() const;

    const TermsVectorType &terms() const;

    typename TermsVectorType::const_iterator begin() const;
    typename TermsVectorType::const_iterator end() const;

    LinearCombination<VarT> linear_combine(const Rational &coeff_this, const Rational &coeff_other, const LinearCombination<VarT> &other);

    bool operator==(const LinearCombination<VarT> &other) const
    {
        return _terms == other._terms;
    }

    bool operator!=(const LinearCombination<VarT> &other) const
    {
        return !(*this == other);
    }

    bool operator<(const LinearCombination<VarT> &other) const
    {
        return _terms < other._terms;
    }

    bool operator>(const LinearCombination<VarT> &other) const
    {
        return _terms > other._terms;
    }

    bool operator<=(const LinearCombination<VarT> &other) const
    {
        return !(*this > other);
    }

    bool operator>=(const LinearCombination<VarT> &other) const
    {
        return !(*this < other);
    }

private:
    TermsVectorType _terms;
};

template <typename VarT>
LinearCombination<VarT> operator*(const Rational &multiplier, const LinearCombination<VarT> &lc);

template <typename VarT>
std::ostream &operator<<(std::ostream &os, const LinearCombination<VarT> &lc)
{
    if (lc.empty())
    {
        os << "0";
        return os;
    }
    bool first_term = true;

    for (const auto &[var, coeff] : lc.terms())
    {
        double cval = coeff.to_double();

        if (!first_term)
        {
            if (cval > 0)
            {
                os << " + ";
            }
            else
            {
                os << " - ";
            }
        }
        else if (cval < 0)
        {
            os << "-";
        }

        Rational abs_coeff = (coeff < Rational(0)) ? -coeff : coeff;
        if (abs_coeff != Rational(1))
        {
            os << abs_coeff;
        }

        if (!(abs_coeff == Rational(1) && (first_term || coeff == Rational(1))))
        {
            os << var;
        }
        else if (abs_coeff == Rational(1))
        {
            os << var;
        }

        first_term = false;
    }

    return os;
}

#endif // LINEAR_COMBINATION_HPP