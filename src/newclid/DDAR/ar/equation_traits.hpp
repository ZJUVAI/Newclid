#ifndef EQUATION_TRAITS_HPP
#define EQUATION_TRAITS_HPP

#include "type/rational.hpp"
#include "type/dist.hpp"
#include "type/round.hpp"
#include "type/slope.hpp"
#include "type/distlog.hpp"
#include "type/product.hpp"

template <typename VarT>
class EquationIndex;

template <typename VarT>
class Equation;

template <typename VarT>
struct EquationTraits
{
    using VarType = VarT;
};

template <>
struct EquationTraits<Slope>
{
    using EvaluationType = double;
    using RHSType = Round;
    static EvaluationType eval_term(const Rational &c, const Slope &v);
};

template <>
struct EquationTraits<DistLog>
{
    using EvaluationType = double;
    using RHSType = Rational;
    static EvaluationType eval_term(const Rational &c, const DistLog &v);
};

template <>
struct EquationTraits<Product>
{
    using EvaluationType = double;
    using RHSType = Rational;
    static EvaluationType eval_term(const Rational &c, const Product &v);
};

template <>
struct EquationTraits<size_t>
{
    using EvaluationType = double;
    static EvaluationType eval_term(const Rational &c, const size_t &v);
};

template <typename VarT>
struct EquationTraits<EquationIndex<VarT>>
{
    using EvaluationType = Equation<VarT>;
    using RHSType = Equation<VarT>;
    static EvaluationType eval_term(const Rational &c, const EquationIndex<VarT> &v)
    {
        return v.equation() * c;
    }
};

#endif // EQUATION_TRAITS_HPP