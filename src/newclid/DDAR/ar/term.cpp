#include "ar/term.hpp"
#include "solver/object_table.hpp"
#include <iomanip>
#include <unordered_map>
#include <map>

using namespace std;

Term::Term(const vector<TermArg> &vars, const Rational &coeff, ObjectTable *table) : _coeff(coeff), _table(table)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
    update();
}

Term::Term(const TermArg &var, const Rational &coeff, ObjectTable *table) : _coeff(coeff), _table(table)
{
    _vars[var] += 1;
    update();
}

Term::Term(const Rational &coeff, ObjectTable *table) : _coeff(coeff), _table(table)
{
}

Term::Term(const vector<TermArg> &vars, ObjectTable *table) : _coeff(1), _table(table)
{
    for (const auto &var : vars)
    {
        _vars[var] += 1;
    }
    update();
}

Term::Term(const TermArg &var, ObjectTable *table) : _coeff(1), _table(table)
{
    _vars[var] += 1;
    update();
}

Term::Term(ObjectTable *table) : _coeff(1), _table(table)
{
}

Term Term::gcd(Term &other) const
{
    update();
    other.update();
    Term res(1, _table);
    for (const auto &[arg, exp] : _vars)
    {
        auto it = other._vars.find(arg);
        if (it != other._vars.end())
        {
            res._vars[arg] = min(exp, it->second);
        }
    }
    for (const auto &[obj, exp] : _actual_vars)
    {
        auto it = other._actual_vars.find(obj);
        if (it != other._actual_vars.end())
        {
            res._actual_vars[obj] = min(exp, it->second);
        }
    }
    res._version = _version;
    return res;
}

Term Term::operator*(const Rational &multiplier) const
{
    update();
    Term res = *this;
    res._coeff *= multiplier;
    return res;
}

Term Term::operator/(const Rational &divisor) const
{
    update();
    Term res = *this;
    res._coeff /= divisor;
    return res;
}

Term &Term::operator*=(const Rational &multiplier)
{
    update();
    _coeff *= multiplier;
    return *this;
}

Term &Term::operator/=(const Rational &divisor)
{
    update();
    _coeff /= divisor;
    return *this;
}

Term Term::operator*(const Term &other) const
{
    update();
    other.update();

    Term res(_coeff * other._coeff, _table);

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
    for (const auto &[obj, exp] : _actual_vars)
    {
        res._actual_vars[obj] += exp;
        if (res._actual_vars[obj] == 0)
        {
            res._actual_vars.erase(obj);
        }
    }
    for (const auto &[obj, exp] : other._actual_vars)
    {
        res._actual_vars[obj] += exp;
        if (res._actual_vars[obj] == 0)
        {
            res._actual_vars.erase(obj);
        }
    }

    res._version = _version;

    return res;
}

Term Term::operator/(const Term &other) const
{
    update();
    other.update();

    Term res(_coeff * other._coeff, _table);

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
    for (const auto &[obj, exp] : _actual_vars)
    {
        res._actual_vars[obj] += exp;
        if (res._actual_vars[obj] == 0)
        {
            res._actual_vars.erase(obj);
        }
    }
    for (const auto &[obj, exp] : other._actual_vars)
    {
        res._actual_vars[obj] -= exp;
        if (res._actual_vars[obj] == 0)
        {
            res._actual_vars.erase(obj);
        }
    }

    res._version = _version;

    return res;
}

Term &Term::operator*=(const Term &other)
{
    update();
    other.update();
    _coeff *= other._coeff;
    for (const auto &[term, exp] : other._vars)
    {
        _vars[term] += exp;
        if (_vars[term] == 0)
        {
            _vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : other._actual_vars)
    {
        _actual_vars[obj] += exp;
        if (_actual_vars[obj] == 0)
        {
            _actual_vars.erase(obj);
        }
    }
    return *this;
}

Term &Term::operator/=(const Term &other)
{
    update();
    other.update();
    _coeff /= other._coeff;
    for (const auto &[term, exp] : other._vars)
    {
        _vars[term] -= exp;
        if (_vars[term] == 0)
        {
            _vars.erase(term);
        }
    }
    for (const auto &[obj, exp] : other._actual_vars)
    {
        _actual_vars[obj] -= exp;
        if (_actual_vars[obj] == 0)
        {
            _actual_vars.erase(obj);
        }
    }
    return *this;
}

Term Term::operator+(const Term &other) const
{
    update();
    other.update();
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
    update();
    other.update();
    if (_vars != other._vars)
    {
        throw runtime_error("Terms are not compatible");
    }
    _coeff += other._coeff;
    return *this;
}

Term Term::operator-() const
{
    update();
    Term res = *this;
    res._coeff = -res._coeff;
    return res;
}

void Term::normalize()
{
    if (_coeff == 0)
    {
        _vars.clear();
        _actual_vars.clear();
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
    for (auto it = _actual_vars.begin(); it != _actual_vars.end();)
    {
        if (it->second == 0)
        {
            it = _actual_vars.erase(it);
        }
        else
        {
            ++it;
        }
    }
}

void Term::update() const
{
    if (!_table || _vars.empty() || _version == _table->version())
    {
        return;
    }
    _actual_vars.clear();

    for (const auto &[arg, exponent] : _vars)
    {
        auto obj = _table->get_or_create_obj(arg);
        if (!obj)
        {
            continue;
        }
        _actual_vars[obj] += exponent;
    }

    for (auto it = _actual_vars.begin(); it != _actual_vars.end();)
    {
        if (it->second == 0)
        {
            it = _actual_vars.erase(it);
        }
        else
        {
            ++it;
        }
    }

    _vars.clear();
    const auto &reverse_map = _table->obj_map_reverse();
    for (const auto &[obj_ptr, exponent] : _actual_vars)
    {
        auto it = reverse_map.find(obj_ptr);
        if (it == reverse_map.end() || it->second.empty())
        {
            continue;
        }

        const vector<TermArg> &args = it->second;
        TermArg min_arg = *min_element(args.begin(), args.end());
        _vars[min_arg] = exponent;
    }

    _version = _table->version();
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
    update();
    other.update();
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
    update();
    other.update();
    return _actual_vars == other._actual_vars;
}

bool Term::operator<(const Term &other) const
{
    update();
    other.update();
    return _actual_vars < other._actual_vars;
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
    term.update();
    os << term.to_string();
    return os;
}

size_t Term::hash() const
{
    size_t seed = std::hash<string>{}(_coeff.to_string());
    update();
    for (const auto &[obj, exp] : _actual_vars)
    {
        size_t h1 = std::hash<Object *>{}(obj.get());
        size_t h2 = std::hash<int>{}(exp);
        seed ^= h1 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= h2 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
    }
    return seed;
}