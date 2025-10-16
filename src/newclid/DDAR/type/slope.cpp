#include "type/slope.hpp"
#include "type/point.hpp"
#include <vector>
#include <iostream>
#include <cmath>

using namespace std;

Slope::Slope(Point p1, Point p2) : _left(min(p1, p2)), _right(max(p1, p2))
{
    // if (_left == _right)
    // {
    //     throw runtime_error("Error: Cannot create Slope for points that are equal.");
    // }
}

bool Slope::check_numerically()
{
    return !_left.is_close(_right);
}

ostream &operator<<(ostream &os, const Slope &slope_angle)
{
    os << "∠(" << slope_angle.left().name() << "-" << slope_angle.right().name() << ")";
    return os;
}

bool Slope::operator<(const Slope &other) const
{
    if (_left == other.left())
    {
        return _right < other._right;
    }
    return _left < other._left;
}

bool Slope::operator==(const Slope &other) const
{
    return _left == other._left && _right == other._right;
}

bool Slope::operator>(const Slope &other) const
{
    return other < *this;
}

double Slope::angle() const
{
    double ang = atan2(_right.y() - _left.y(), _right.x() - _left.x());

    if (ang < 0)
    {
        ang += M_PI;
    }

    if (Numerical::close_enough(ang, M_PI))
    {
        return 0.0;
    }

    return ang;
}

Slope Slope::normalize() const
{
    if (_left > _right)
    {
        return Slope(_right, _left);
    }
    return *this; 
}