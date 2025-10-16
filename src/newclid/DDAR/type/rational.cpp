#include "type/rational.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <limits>

using namespace std;

void Rational::normalize()
{
    if (_den == 0)
    {
        throw runtime_error("Denominator cannot be zero");
    }
    if (_den < 0)
    {
        _den = -_den;
        _num = -_num;
    }
    long long g = gcd(_num, _den);
    if (g != 0)
    {
        _num /= g;
        _den /= g;
    }

    if (_den < 0)
    {
        _num = -_num;
        _den = -_den;
    }
}

Rational::Rational() : _num(0), _den(1) {}

Rational::Rational(long long num) : _num(num), _den(1) {}

Rational::Rational(int num) : _num(num), _den(1) {}

Rational::Rational(long long num, long long den) : _num(num), _den(den)
{
    normalize();
}

Rational::Rational(double value, long long maxDen)
{
    long long a0 = static_cast<long long>(floor(value));
    double frac = value - a0;

    if (abs(frac) < 1e-12)
    {
        _num = a0;
        _den = 1;
        return;
    }

    long long h1 = 1, h2 = 0;
    long long k1 = 0, k2 = 1;
    double b = value;

    while (true)
    {
        long long a = static_cast<long long>(floor(b));
        long long h = a * h1 + h2;
        long long k = a * k1 + k2;
        if (k > maxDen)
            break;
        h2 = h1;
        h1 = h;
        k2 = k1;
        k1 = k;
        if (abs(b - a) < 1e-12)
            break;
        b = 1.0 / (b - a);
    }

    _num = h1;
    _den = k1;
    normalize();
}

Rational Rational::operator+(const Rational &rhs) const
{
    return Rational(_num * rhs._den + rhs._num * _den, _den * rhs._den);
}

Rational Rational::operator-(const Rational &rhs) const
{
    return Rational(_num * rhs._den - rhs._num * _den, _den * rhs._den);
}

Rational Rational::operator*(const Rational &rhs) const
{
    return Rational(_num * rhs._num, _den * rhs._den);
}

Rational Rational::operator/(const Rational &rhs) const
{
    if (rhs._num == 0)
    {
        throw runtime_error("Division by zero in Rational");
    }
    return Rational(_num * rhs._den, _den * rhs._num);
}

Rational &Rational::operator+=(const Rational &rhs)
{
    *this = *this + rhs;
    return *this;
}
Rational &Rational::operator-=(const Rational &rhs)
{
    *this = *this - rhs;
    return *this;
}
Rational &Rational::operator*=(const Rational &rhs)
{
    *this = *this * rhs;
    return *this;
}
Rational &Rational::operator/=(const Rational &rhs)
{
    *this = *this / rhs;
    return *this;
}

bool Rational::operator==(const Rational &rhs) const
{
    return _num == rhs._num && _den == rhs._den;
}

bool Rational::operator<(const Rational &rhs) const
{
    return _num * rhs._den < rhs._num * _den;
}

ostream &operator<<(ostream &os, const Rational &r)
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

string Rational::to_string() const
{
    if (_den == 1)
    {
        return std::to_string(_num);
    }
    else
    {
        return std::to_string(_num) + "/" + std::to_string(_den);
    }
}

long long gcd(long long a, long long b)
{
    while (b != 0)
    {
        long long t = b;
        b = a % b;
        a = t;
    }
    return a;
}