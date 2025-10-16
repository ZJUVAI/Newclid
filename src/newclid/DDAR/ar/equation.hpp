#ifndef EQUATION_HPP
#define EQUATION_HPP

#include "ar/linear_combination.hpp"
#include "ar/equation_traits.hpp"
#include "ar/equation_index.hpp"

template <typename VarT>
class Equation final
{
public:
    using VarType = VarT;
    using LinearCombinationType = LinearCombination<VarT>;
    using RHSType = typename EquationTraits<VarType>::RHSType;

private:
    LinearCombinationType _lhs;
    RHSType _rhs;

public:
    Equation() = default;

    Equation(LinearCombinationType lhs, RHSType rhs);

    const LinearCombinationType &lhs() const { return _lhs; }

    const RHSType &rhs() const { return _rhs; }

    Equation &operator+=(const Equation &other);
    Equation operator+(const Equation &other) const;

    Equation &operator-=(const Equation &other);
    Equation operator-(const Equation &other) const;

    Equation &operator*=(const Rational &multiplier);
    Equation operator*(const Rational &multiplier) const;

    Equation operator-() const;

    std::pair<Rational, Equation> normalize() const;

    bool check_numerically() const
    {
        // return lhs().evaluate() == RHSType(_rhs);
        return true;
    }

    bool operator==(const Equation &other) const
    {
        return _lhs == other._lhs && _rhs == other._rhs;
    }

    bool operator!=(const Equation &other) const
    {
        return !(*this == other);
    }

    bool operator<(const Equation &other) const
    {
        return _lhs < other._lhs ||
               (_lhs == other._lhs && _rhs < other._rhs);
    }

    bool operator>(const Equation &other) const
    {
        return _lhs > other._lhs ||
               (_lhs == other._lhs && _rhs > other._rhs);
    }

    bool operator<=(const Equation &other) const
    {
        return !(*this > other);
    }

    bool operator>=(const Equation &other) const
    {
        return !(*this < other);
    }

    bool is_empty() const;

    static Equation sub_eq_const(const VarT &a, const VarT &b, const RHSType &rhs = {});
    static Equation sub_eq_sub(const VarT &a, const VarT &b, const VarT &c, const VarT &d, const RHSType &rhs = {});
};

template <typename VarT>
std::ostream &operator<<(std::ostream &os, const Equation<VarT> &eq)
{
    os << eq.lhs() << " = " << eq.rhs();
    return os;
}

template <typename VarT>
Equation<VarT> operator==(const LinearCombination<VarT> &lhs, const typename EquationTraits<VarT>::RHSType &rhs)
{
    return Equation<VarT>(lhs, rhs);
}

template <typename VarT>
bool eq_numerically(const Equation<VarT> &left, const Equation<VarT> &right);

namespace std
{
    template <typename VarT>
    struct hash<Equation<VarT>>
    {
        size_t operator()(const Equation<VarT> &eq) const;
    };
}

#endif // EQUATION_HPP