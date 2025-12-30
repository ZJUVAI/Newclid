#include "ar/equation.hpp"
#include "ar/equation_index.hpp"
#include "ar/term.hpp"

using namespace std;

Equation::Equation(vector<Term> terms, ObjectTable *table) : _combination({std::make_pair(1.0, EquationIndex(-1, nullptr))}), _table(std::move(table))
{
    for (auto &term : terms)
    {
        auto it = std::find(_terms.begin(), _terms.end(), term);

        if (it == _terms.end())
        {
            _terms.push_back(term);
        }
        else
        {
            *it += term;
        }
    }
    this->normalize();
}

Equation &Equation::operator+=(const Equation &other)
{
    for (auto &term : other._terms)
    {
        bool merged = false;
        for (auto &my_term : _terms)
        {
            if (my_term == term)
            {
                my_term += term;
                merged = true;
                break;
            }
        }
        if (!merged)
        {
            _terms.push_back(term);
        }
    }

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
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    for (auto &comb : _combination)
    {
        comb.first *= multiplier.to_double();
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
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    for (auto &comb : _combination)
    {
        comb.first *= multiplier.to_double();
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
    for (auto &term : res._terms)
    {
        term = -term;
    }
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
        if (Numerical::close_enough(it->first, 0.0))
        {
            it = _combination.erase(it);
        }
        else
        {
            ++it;
        }
    }
    for (auto it = _terms.begin(); it != _terms.end();)
    {
        if (it->is_zero())
        {
            it = _terms.erase(it);
        }
        else
        {
            ++it;
        }
    }
    if (_terms.size() == 1 && _terms[0].is_pi())
    {
        _terms.clear();
        return;
    }
    if (_terms.size() == 0)
    {
        return;
    }
    sort(_terms.begin(), _terms.end());
    reverse(_terms.begin(), _terms.end());
    Rational r = Rational(1) / (*_terms.begin()).coeff();
    for (auto &term : _terms)
    {
        term *= r;
    }
    for (auto &comb : _combination)
    {
        comb.first *= r.to_double();
    }
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
    if (_terms.empty())
    {
        return;
    }

    Term common = _terms[0];

    for (size_t i = 1; i < _terms.size(); ++i)
    {
        common = common.gcd(_terms[i]);
        if (common.is_one())
        {
            break;
        }
    }

    if (!common.is_one())
    {
        for (auto &t : _terms)
            t = t / common;
        for (auto &c : _combination)
            c.first /= common.to_double();
    }

    return;
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