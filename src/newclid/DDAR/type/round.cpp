#include "type/round.hpp"
#include "type/rational.hpp"
#include <cmath>

using namespace std;

void Round::normalize()
{
    // 确保分母为正
    if (_den == 0)
    {
        throw runtime_error("Denominator cannot be zero");
    }
    if (_den < 0)
    {
        _den = -_den;
        _num = -_num;
    }

    // 计算最大公约数并约分
    long long g = gcd(_num, _den);
    if (g != 0)
    {
        _num /= g;
        _den /= g;
    }

    if (_den < 0)
    {
        _den = -_den;
        _num = -_num;
    }

    // 将值限制在[0, 1)范围内
    while (_num < 0)
    {
        _num += _den;
    }

    while (_num >= _den)
    {
        _num -= _den;
    }
}

Round::Round() : _num(0), _den(1) {}

Round::Round(long long num) : _num(0), _den(1) {}

Round::Round(int num) : _num(0), _den(1) {}

Round::Round(long long num, long long den) : _num(num), _den(den)
{
    normalize();
}

Round::Round(double value, long long maxDen)
{
    *this = Rational(value, maxDen);
    normalize();
}

Round::Round(Rational r) : _num(r.numerator()), _den(r.denominator())
{
    normalize();
}

Round Round::operator+(const Round &r) const
{
    return Round(_num * r._den + r._num * _den, _den * r._den);
}

Round Round::operator-(const Round &r) const
{
    return Round(_num * r._den - r._num * _den, _den * r._den);
}

Round Round::operator*(const Round &r) const
{
    return Round(_num * r._num, _den * r._den);
}

Round Round::operator/(const Round &r) const
{
    if (r.numerator() == 0)
    {
        throw runtime_error("Division by zero in Rational");
    }
    return Round(_num * r._den, _den * r._num);
}

Round &Round::operator+=(const Round &r)
{
    *this = *this + r;
    return *this;
}

Round &Round::operator-=(const Round &r)
{
    *this = *this - r;
    return *this;
}

Round &Round::operator*=(const Round &r)
{
    *this = *this * r;
    return *this;
}

Round &Round::operator/=(const Round &r)
{
    *this = *this / r;
    return *this;
}

bool Round::operator==(const Round &rhs) const
{
    return _num == rhs._num && _den == rhs._den;
}

bool Round::operator<(const Round &rhs) const
{
    return _num * rhs._den < _den * rhs._num;
}

bool Round::operator==(const Rational &rhs) const
{
    Round r = Round(rhs);
    return *this == r;
}

ostream &operator<<(ostream &os, const Round &r)
{
    if (r._den == 1)
    {
        os << r._num;
    }
    else
    {
        os << r._num << "/" << r._den;
    }
    return os;
}