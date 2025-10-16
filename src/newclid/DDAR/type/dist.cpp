#include "type/dist.hpp"
#include <iostream>
#include <cmath>
using namespace std;

Dist::Dist(Point p1, Point p2) : _left(min(p1, p2)), _right(max(p1, p2))
{
}

double Dist::to_double() const
{
    return sqrt(pow(_left.x() - _right.x(), 2) + pow(_left.y() - _right.y(), 2));
}

ostream &operator<<(std::ostream &os, const Dist &dist)
{
    os << "|" << dist.left().name() << "-" << dist.right().name() << "|";
    return os;
}

bool Dist::operator<(const Dist &other) const
{
    if (_left == other._left)
    {
        return _right < other._right;
    }
    return _left < other._left;
}

bool Dist::operator==(const Dist &other) const
{
    return _left == other._left && _right == other._right;
}

bool Dist::operator>(const Dist &other) const
{
    if (_left == other._left)
    {
        return _right > other._right;
    }
    return _left > other._left;
}

Dist Dist::normalize() const
{
    if (_left < _right)
    {
        return Dist(_left, _right);
    }
    return Dist(_right, _left);
}