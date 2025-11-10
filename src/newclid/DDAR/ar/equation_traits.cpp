#include "ar/equation_traits.hpp"
#include "type/rational.hpp"

double EquationTraits<Slope>::eval_term(const Rational &c, const Slope &v)
{
    return c.to_double() * v.angle();
}

double EquationTraits<DistLog>::eval_term(const Rational &c, const DistLog &v)
{
    return c.to_double() * v.to_double();
}

double EquationTraits<Product>::eval_term(const Rational &c, const Product &v)
{ 
    return c.to_double() * v.to_double();
}

double EquationTraits<size_t>::eval_term(const Rational &c, const size_t &v)
{
    return c.to_double() * v;
}