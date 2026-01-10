#include "ar/term.hpp"
#include "solver/object_table.hpp"
#include <iomanip>
#include <unordered_map>
#include <map>

using namespace std;

Term::Term(const vector<TermArg> &vars, const Rational &coeff) : _coeff(coeff)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
}

Term::Term(const TermArg &var, const Rational &coeff) : _coeff(coeff)
{
    _vars[var] += 1;
}

Term::Term(const Rational &coeff) : _coeff(coeff)
{
}

Term::Term(const vector<TermArg> &vars) : _coeff(1)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
}

Term::Term(const TermArg &var) : _coeff(1)
{
    _vars[var] += 1;
}

Term::Term() : _coeff(1)
{
}

Term Term::gcd(Term &other) const
{
    Term res(1);
    for (const auto &[arg, exp] : _vars)
    {
        auto it = other._vars.find(arg);
        if (it != other._vars.end())
        {
            res._vars[arg] = min(exp, it->second);
        }
    }
    for (const auto &[obj, exp] : _vars)
    {
        auto it = other._vars.find(obj);
        if (it != other._vars.end())
        {
            res._vars[obj] = min(exp, it->second);
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
    Term res(_coeff * other._coeff);

    for (const auto &[term, exp] : _vars)
    {
        res._vars[term] += exp;
        if (res._vars[term] == 0)
        {
            res._vars.erase(term);
        }
    }
    for (const auto &[term, exp] : other._vars)
    {
        res._vars[term] += exp;
        if (res._vars[term] == 0)
        {
            res._vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : _vars)
    {
        res._vars[obj] += exp;
        if (res._vars[obj] == 0)
        {
            res._vars.erase(obj);
        }
    }
    for (const auto &[obj, exp] : other._vars)
    {
        res._vars[obj] += exp;
        if (res._vars[obj] == 0)
        {
            res._vars.erase(obj);
        }
    }

    return res;
}

Term Term::operator/(const Term &other) const
{

    Term res(_coeff * other._coeff);

    for (const auto &[term, exp] : _vars)
    {
        res._vars[term] += exp;
        if (res._vars[term] == 0)
        {
            res._vars.erase(term);
        }
    }
    for (const auto &[term, exp] : other._vars)
    {
        res._vars[term] -= exp;
        if (res._vars[term] == 0)
        {
            res._vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : _vars)
    {
        res._vars[obj] += exp;
        if (res._vars[obj] == 0)
        {
            res._vars.erase(obj);
        }
    }
    for (const auto &[obj, exp] : other._vars)
    {
        res._vars[obj] -= exp;
        if (res._vars[obj] == 0)
        {
            res._vars.erase(obj);
        }
    }

    return res;
}

Term &Term::operator*=(const Term &other)
{
    _coeff *= other._coeff;
    for (const auto &[term, exp] : other._vars)
    {
        _vars[term] += exp;
        if (_vars[term] == 0)
        {
            _vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : other._vars)
    {
        _vars[obj] += exp;
        if (_vars[obj] == 0)
        {
            _vars.erase(obj);
        }
    }
    return *this;
}

Term &Term::operator/=(const Term &other)
{
    _coeff /= other._coeff;
    for (const auto &[term, exp] : other._vars)
    {
        _vars[term] -= exp;
        if (_vars[term] == 0)
        {
            _vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : other._vars)
    {
        _vars[obj] -= exp;
        if (_vars[obj] == 0)
        {
            _vars.erase(obj);
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
    if (_coeff == 0)
    {
        _vars.clear();
        _vars.clear();
        return;
    }
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
    for (auto &pair : other._vars)
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
    return other < *this;
}

bool Term::operator<=(const Term &other) const
{
    return !(other < *this);
}

bool Term::operator>=(const Term &other) const
{
    return !(*this < other);
}

bool Term::operator!=(const Term &other) const
{
    return !(*this == other);
}

ostream &operator<<(ostream &os, const Term &term)
{
    os << term.to_string();
    return os;
}

size_t Term::hash() const
{
    size_t seed = std::hash<string>{}(_coeff.to_string());
    for (const auto &[obj, exp] : _vars)
    {
        size_t h1 = std::hash<string>{}(obj.to_string());
        size_t h2 = std::hash<int>{}(exp);
        seed ^= h1 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= h2 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
    }
    return seed;
}