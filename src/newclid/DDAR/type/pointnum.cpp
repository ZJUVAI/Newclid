#include "type/pointnum.hpp"
#include "numerical.hpp"
#include <string>
#include <cmath>

using namespace std;

PointNum::PointNum(double x, double y) : _x(x), _y(y) {}

double PointNum::x() const
{
    return _x;
}

double PointNum::y() const
{
    return _y;
}

PointNum PointNum::operator+(const PointNum &other) const
{
    return PointNum(_x + other.x(), _y + other.y());
}

PointNum PointNum::operator-(const PointNum &other) const
{
    return PointNum(_x - other.x(), _y - other.y());
}

PointNum PointNum::operator*(double scalar) const
{
    return PointNum(_x * scalar, _y * scalar);
}

double PointNum::operator*(const PointNum &other) const
{
    return _x * other.x() + _y * other.y();
}

PointNum PointNum::operator/(double scalar) const
{
    return PointNum(_x / scalar, _y / scalar);
}

string PointNum::to_string() const
{
    return "PointNum(" + std::to_string(_x) + ", " + std::to_string(_y) + ")";
}

double PointNum::abs() const
{
    return sqrt(_x * _x + _y * _y);
}

double PointNum::angle() const
{
    return atan2(_y, _x);
}

bool PointNum::close_enough(const PointNum &other) const
{
    return Numerical::close_enough(_x, other.x()) && Numerical::close_enough(_y, other.y());
}

double PointNum::distance(const PointNum &other) const
{
    return (other - *this).abs();
}

double PointNum::distance2(const PointNum &other) const
{
    return (other - *this) * (other - *this);
}

void PointNum::rotate(double angle)
{
    double x = _x * cos(angle) - _y * sin(angle);
    double y = _x * sin(angle) + _y * cos(angle);
    _x = x;
    _y = y;
}