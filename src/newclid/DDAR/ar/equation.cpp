#include "ar/equation.hpp"
#include "ar/equation_index.hpp"
#include "ar/term.hpp"

using namespace std;

Equation &Equation::operator+=(const Equation &other)
{
    _terms += other._terms;
    for (const auto &comb : other._combination)
    {
        bool merged = false;
        for (auto &my_comb : _combination)
        {
            if (my_comb.second == comb.second)
            {
                my_comb.first += comb.first;
                merged = true;
                break;
            }
        }
        if (!merged)
        {
            _combination.push_back(comb);
        }
    }
    this->normalize();
    return *this;
}

Equation Equation::operator+(const Equation &other) const
{
    Equation res = *this;
    res += other;
    res.normalize();
    return res;
}

Equation &Equation::operator-=(const Equation &other)
{
    return *this += -other;
}

Equation Equation::operator-(const Equation &other) const
{
    Equation res = *this;
    res -= other;
    res.normalize();
    return res;
}

Equation &Equation::operator*=(const Rational &multiplier)
{
    _terms *= multiplier;
    for (auto &comb : _combination)
    {
        comb.first *= multiplier;
    }
    return *this;
}

Equation Equation::operator*(const Rational &multiplier) const
{
    Equation res = *this;
    res *= multiplier;
    return res;
}

Equation &Equation::operator*=(const Term &multiplier)
{
    _terms *= multiplier;
    for (auto &comb : _combination)
    {
        comb.first *= multiplier;
    }
    return *this;
}

Equation Equation::operator*(const Term &multiplier) const
{
    Equation res = *this;
    res *= multiplier;
    return res;
}

Equation Equation::operator-() const
{
    Equation res = *this;
    res._terms = -_terms;
    for (auto &comb : res._combination)
    {
        comb.first = -comb.first;
    }
    return res;
}

bool Equation::empty() const
{
    return _terms.empty();
}

bool Equation::linear() const
{
    for (const auto &term : _terms)
    {
        if (term.degree() > 1 || term.degree() < 0)
        {
            return false;
        }
    }
    return true;
}

bool Equation::check_numerically() const
{
    double res = 0.0;
    for (const auto &term : _terms)
    {
        res += term.to_double();
    }
    return Numerical::close_enough(res, 0.0);
}

void Equation::normalize()
{
    for (auto it = _combination.begin(); it != _combination.end();)
    {
        it->first.normalize();
        if (it->first.empty())
        {
            it = _combination.erase(it);
        }
        else
        {
            ++it;
        }
    }

    if (_terms.empty())
    {
        return;
    }

    Rational r = Rational(1) / _terms.terms().front().coeff();
    *this *= r;
}

void Equation::set_index(int n, LinearSystem *system)
{
    EquationIndex index(n, system);
    for (auto &comb : _combination)
    {
        if (!comb.second.is_valid())
        {
            comb.second = index;
            break;
        }
    }
}

void Equation::reduction()
{
    Term common = _terms.gcd();
    Term r = Term() / common;
    *this *= r;
}

std::vector<Term>::const_iterator Equation::begin() const
{
    return _terms.begin();
}

std::vector<Term>::const_iterator Equation::end() const
{
    return _terms.end();
}

ostream &operator<<(ostream &os, const Equation &eq)
{
    bool first = true;
    for (const auto &term : eq.terms())
    {
        if (!first)
        {
            os << " + ";
        }
        os << term;
        first = false;
    }
    os << " = 0 ( ";
    for (const auto &comb : eq.combination())
    {
        if (!comb.second.is_valid())
        {
            os << comb.first << "*Eq<*> ";
        }
        else
        {
            os << comb.first << "*Eq" << comb.second << " ";
        }
    }
    os << ")";
    return os;
}