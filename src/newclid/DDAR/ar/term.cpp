#include "ar/term.hpp"
#include "typedef.hpp"
#include <map>

using namespace std;

Term::Term(const std::vector<term_arg> &vars, const Rational &coeff) : _coeff(coeff)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
}

Term::Term(const term_arg &var, const Rational &coeff) : _coeff(coeff)
{
    _vars[var] += 1;
}

Term::Term(const Rational &coeff) : _coeff(coeff)
{
}

Term::Term(const std::vector<term_arg> &vars) : _coeff(1)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
}

Term::Term(const term_arg &var) : _coeff(1)
{
    _vars[var] += 1;
}

Term::Term() : _coeff(1)
{
}

Term Term::gcd(const Term &other) const
{
    Term res;
    for (const auto &pair : _vars)
    {
        if (other._vars.count(pair.first))
        {
            res._vars[pair.first] = std::min(pair.second, other._vars.at(pair.first));
        }
    }
    return res;
}

Term Term::operator*(const Rational &multiplier) const
{
    Term res = *this;
    res._coeff *= multiplier;
    return res;
}

Term Term::operator/(const Rational &divisor) const
{
    Term res = *this;
    res._coeff /= divisor;
    return res;
}

Term &Term::operator*=(const Rational &multiplier)
{
    _coeff *= multiplier;
    return *this;
}

Term &Term::operator/=(const Rational &divisor)
{
    _coeff /= divisor;
    return *this;
}

Term Term::operator*(const Term &other) const
{
    Term res = *this;
    res._coeff *= other._coeff;
    for (const auto &pair : other._vars)
    {
        res._vars[pair.first] += pair.second;
        if (res._vars[pair.first] == 0)
        {
            res._vars.erase(pair.first);
        }
    }
    return res;
}

Term Term::operator/(const Term &other) const
{
    Term res = *this;
    res._coeff /= other._coeff;
    for (const auto &pair : other._vars)
    {
        res._vars[pair.first] -= pair.second;
        if (res._vars[pair.first] == 0)
        {
            res._vars.erase(pair.first);
        }
    }
    return res;
}

Term &Term::operator*=(const Term &other)
{
    _coeff *= other._coeff;
    for (const auto &pair : other._vars)
    {
        _vars[pair.first] += pair.second;
        if (_vars[pair.first] == 0)
        {
            _vars.erase(pair.first);
        }
    }
    return *this;
}

Term &Term::operator/=(const Term &other)
{
    _coeff /= other._coeff;
    for (const auto &pair : other._vars)
    {
        _vars[pair.first] -= pair.second;
        if (_vars[pair.first] == 0)
        {
            _vars.erase(pair.first);
        }
    }
    return *this;
}

Term Term::operator+(const Term &other) const
{
    if (_vars != other._vars)
    {
        throw runtime_error("Terms are not compatible");
    }
    Term res = *this;
    res._coeff += other._coeff;
    return res;
}

Term &Term::operator+=(const Term &other)
{
    if (_vars != other._vars)
    {
        throw runtime_error("Terms are not compatible");
    }
    _coeff += other._coeff;
    return *this;
}

Term Term::operator-() const
{
    Term res = *this;
    res._coeff = -res._coeff;
    return res;
}
void Term::normalize()
{
    for (auto it = _vars.begin(); it != _vars.end();)
    {
        if (it->second == 0)
        {
            it = _vars.erase(it);
        }
        else
        {
            ++it;
        }
    }
}

void Term::round()
{
    while (_coeff > 1)
    {
        _coeff -= 1;
    }
    while (_coeff < 0)
    {
        _coeff += 1;
    }
}

int Term::degree() const
{
    int res = 0;
    for (const auto &pair : _vars)
    {
        res += pair.second;
    }
    return res;
}

double Term::to_double() const
{
    double res = _coeff.to_double();
    for (const auto &pair : _vars)
    {
        res *= pow(pair.first.to_double(), pair.second);
    }
    return res;
}

string Term::to_string() const
{
    string res = _coeff.to_string();
    for (const auto &pair : _vars)
    {
        if (pair.second == 1)
        {
            res += " * " + pair.first.to_string();
        }
        else
        {
            res += " * " + pair.first.to_string() + "^" + std::to_string(pair.second);
        }
    }
    return res;
}

bool Term::contain(const Term &other) const
{
    for (const auto &pair : other._vars)
    {
        if (_vars.count(pair.first) == 0)
        {
            return false;
        }
        if (_vars.at(pair.first) < pair.second)
        {
            return false;
        }
    }
    return true;
}

bool Term::operator==(const Term &other) const
{
    return _vars == other._vars;
}

bool Term::operator<(const Term &other) const
{
    return _vars < other._vars;
}

bool Term::operator>(const Term &other) const
{
    return _vars > other._vars;
}

bool Term::operator<=(const Term &other) const
{
    return _vars <= other._vars;
}

bool Term::operator>=(const Term &other) const
{
    return _vars >= other._vars;
}

bool Term::operator!=(const Term &other) const
{
    return _vars != other._vars;
}

ostream &operator<<(ostream &os, const Term &term)
{
    os << term.to_string();
    return os;
}