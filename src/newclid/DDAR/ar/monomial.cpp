#include "ar/monomial.hpp"
#include "numerical.hpp"
#include <cmath>
#include <stdexcept>
#include <algorithm>
#include <sstream>

using namespace std;

Monomial::Monomial(const TermArg &var, int exp)
{
    if (exp != 0)
    {
        _vars[var] = exp;
    }
}

Monomial::Monomial(const vector<TermArg> &vars)
{
    for (const auto &v : vars)
    {
        _vars[v] += 1;
    }
    prune_zero_exponents();
}

void Monomial::prune_zero_exponents()
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

Monomial Monomial::operator*(const Monomial &other) const
{
    Monomial res = *this;
    res *= other;
    return res;
}

Monomial &Monomial::operator*=(const Monomial &other)
{
    for (const auto &[var, exp] : other._vars)
    {
        _vars[var] += exp;
        if (_vars[var] == 0)
        {
            _vars.erase(var);
        }
    }
    return *this;
}

Monomial Monomial::operator/(const Monomial &other) const
{
    Monomial res = *this;
    res /= other;
    return res;
}

Monomial &Monomial::operator/=(const Monomial &other)
{
    for (const auto &[var, exp] : other._vars)
    {
        _vars[var] -= exp;
        if (_vars[var] == 0)
        {
            _vars.erase(var);
        }
    }
    return *this;
}

bool Monomial::divides(const Monomial &other) const
{
    // *this 整除 other，当且仅当 *this 的每个变量都在 other 中出现，
    // 且指数不小于 *this 中的指数。
    for (const auto &[var, exp] : _vars)
    {
        auto it = other._vars.find(var);
        if (it == other._vars.end() || it->second < exp)
        {
            return false;
        }
    }
    return true;
}

Monomial Monomial::gcd(const Monomial &other) const
{
    Monomial res;
    for (const auto &[var, exp] : _vars)
    {
        auto it = other._vars.find(var);
        if (it != other._vars.end())
        {
            int m = std::min(exp, it->second);
            if (m != 0)
            {
                res._vars[var] = m;
            }
        }
    }
    return res;
}

Monomial Monomial::lcm(const Monomial &other) const
{
    Monomial res = *this;
    for (const auto &[var, exp] : other._vars)
    {
        auto it = res._vars.find(var);
        if (it == res._vars.end())
        {
            res._vars[var] = exp;
        }
        else
        {
            it->second = std::max(it->second, exp);
        }
    }
    return res;
}

Monomial Monomial::inverse() const
{
    Monomial res;
    for (const auto &[var, exp] : _vars)
    {
        res._vars[var] = -exp;
    }
    return res;
}

int Monomial::degree() const
{
    int res = 0;
    for (const auto &[var, exp] : _vars)
    {
        res += exp;
    }
    return res;
}

double Monomial::to_double() const
{
    double res = 1.0;
    for (const auto &[var, exp] : _vars)
    {
        res *= std::pow(var.to_double(), exp);
    }
    return res;
}

string Monomial::to_string() const
{
    if (_vars.empty())
    {
        return "1";
    }
    ostringstream oss;
    bool first = true;
    for (const auto &[var, exp] : _vars)
    {
        if (!first)
        {
            oss << "*";
        }
        oss << var.to_string();
        if (exp != 1)
        {
            oss << "^" << exp;
        }
        first = false;
    }
    return oss.str();
}

// 按最大变量的 degree-lex 风格排序，与旧 Term::operator< 一致。
// 常数单项式最小。
bool Monomial::operator<(const Monomial &other) const
{
    if (_vars.empty())
    {
        return !other._vars.empty();
    }
    if (other._vars.empty())
    {
        return false;
    }
    const auto &max1 = *_vars.rbegin();
    const auto &max2 = *other._vars.rbegin();
    if (max1.first != max2.first)
    {
        return max1.first < max2.first;
    }
    if (max1.second != max2.second)
    {
        return max1.second < max2.second;
    }
    return _vars < other._vars;
}

size_t Monomial::hash() const
{
    size_t seed = 0;
    for (const auto &[var, exp] : _vars)
    {
        seed ^= std::hash<TermArg>{}(var) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= std::hash<int>{}(exp) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
    }
    return seed;
}

ostream &operator<<(ostream &os, const Monomial &m)
{
    os << m.to_string();
    return os;
}
