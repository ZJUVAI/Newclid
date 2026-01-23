#include "ar/linear_combination.hpp"
#include "ar/equation_index.hpp"
#include "ar/term.hpp"

using namespace std;

LinearCombination::LinearCombination(vector<Term> terms)
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

LinearCombination &LinearCombination::operator+=(const LinearCombination &other)
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
    this->normalize();
    return *this;
}

LinearCombination LinearCombination::operator+(const LinearCombination &other) const
{
    LinearCombination res = *this;
    res += other;
    res.normalize();
    return res;
}

LinearCombination &LinearCombination::operator-=(const LinearCombination &other)
{
    return *this += -other;
}

LinearCombination LinearCombination::operator-(const LinearCombination &other) const
{
    LinearCombination res = *this;
    res -= other;
    res.normalize();
    return res;
}

LinearCombination &LinearCombination::operator*=(const Rational &multiplier)
{
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    return *this;
}

LinearCombination LinearCombination::operator*(const Rational &multiplier) const
{
    LinearCombination res = *this;
    res *= multiplier;
    return res;
}

LinearCombination &LinearCombination::operator*=(const Term &multiplier)
{
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    return *this;
}

LinearCombination LinearCombination::operator*(const Term &multiplier) const
{
    LinearCombination res = *this;
    res *= multiplier;
    return res;
}

LinearCombination LinearCombination::operator-() const
{
    LinearCombination res = *this;
    for (auto &term : res._terms)
    {
        term = -term;
    }
    return res;
}

void LinearCombination::normalize()
{
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

    sort(_terms.begin(), _terms.end());
}

Term LinearCombination::gcd()
{

    if (_terms.empty())
    {
        return Term();
    }

    Term common = _terms[0];

    for (size_t i = 0; i < _terms.size(); ++i)
    {
        common = common.gcd(_terms[i]);
        if (common.is_one())
        {
            return common;
        }
    }

    return common;
}

std::vector<Term>::const_iterator LinearCombination::begin() const
{
    return _terms.begin();
}

std::vector<Term>::const_iterator LinearCombination::end() const
{
    return _terms.end();
}

ostream &operator<<(ostream &os, const LinearCombination &eq)
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
    return os;
}