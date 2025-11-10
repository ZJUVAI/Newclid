#include "ar/equation.hpp"
#include "ar/equation_traits.hpp"
#include "ar/linear_combination.hpp"
#include <sstream>

using namespace std;

template <typename VarT>
Equation<VarT>::Equation(LinearCombinationType lhs, RHSType rhs) : _lhs(move(lhs)),
                                                                   _rhs(move(rhs)) {}

template <typename VarT>
Equation<VarT> &Equation<VarT>::operator+=(const Equation &other)
{
    _lhs += other.lhs();
    _rhs += other.rhs();
    return *this;
}

template <typename VarT>
Equation<VarT> &Equation<VarT>::operator-=(const Equation &other)
{
    _lhs -= other.lhs();
    _rhs -= other.rhs();
    return *this;
}

template <typename VarT>
Equation<VarT> &Equation<VarT>::operator*=(const Rational &multiplier)
{
    _lhs *= multiplier;
    _rhs *= multiplier;
    return *this;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::operator+(const Equation &other) const
{
    Equation<VarT> result = *this;
    result += other;
    return result;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::operator-(const Equation &other) const
{
    Equation<VarT> result = *this;
    result -= other;
    return result;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::operator*(const Rational &multiplier) const
{
    Equation<VarT> result = *this;
    result *= multiplier;
    return result;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::operator-() const
{
    return Equation<VarT>(-_lhs, -_rhs);
}

template <typename VarT>
pair<Rational, Equation<VarT>> Equation<VarT>::normalize() const
{
    if (_lhs.empty())
    {
        return {1, *this};
    }
    Rational const coeff = Rational(1) / _lhs.begin()->second;
    return {coeff, *this * coeff};
}

template <typename VarT>
bool Equation<VarT>::is_empty() const
{
    return _lhs.empty() && _rhs == RHSType();
}

template <typename VarT>
bool eq_numerically(const Equation<VarT> &left, const Equation<VarT> &right)
{
    return left == right;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::sub_eq_const(const VarT &a, const VarT &b, const typename Equation<VarT>::RHSType &rhs)
{
    return LinearCombination<VarT>(a) - LinearCombination<VarT>(b) == rhs;
}

template <typename VarT>
Equation<VarT> Equation<VarT>::sub_eq_sub(const VarT &a, const VarT &b, const VarT &c, const VarT &d, const typename Equation<VarT>::RHSType &rhs)
{
    return LinearCombination<VarT>(a) - LinearCombination<VarT>(b) - LinearCombination<VarT>(c) + LinearCombination<VarT>(d) == rhs;
}

namespace std
{
    template <typename VarT>
    size_t hash<Equation<VarT>>::operator()(const Equation<VarT> &eq) const
    {
        std::ostringstream oss;
        return std::hash<std::string>{}(oss.str());
    }
}

template class Equation<Slope>;
template class Equation<DistLog>;
template class Equation<Product>;

template class Equation<EquationIndex<Slope>>;
template class Equation<EquationIndex<DistLog>>;
template class Equation<EquationIndex<Product>>;

template class hash<Equation<Slope>>;
template class hash<Equation<DistLog>>;
template class hash<Equation<Product>>;