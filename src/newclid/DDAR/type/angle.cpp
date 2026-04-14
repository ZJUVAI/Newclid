#include "type/angle.hpp"
#include "type/point.hpp"
#include "predicate/coll.hpp"

#include <iostream>
#include <vector>

using namespace std;

Angle::Angle(Point left_pt, Point vertex_pt, Point right_pt)
    : _left_pt(left_pt), _vertex_pt(vertex_pt), _right_pt(right_pt)
{
    // if (_vertex_pt == _left_pt || _vertex_pt == _right_pt)
    // {
    //     throw runtime_error("Error: Invalid vertex point.");
    // }
}

Angle::Angle(Point p1, Point p2, Point p3, Point p4) : _left_pt(p1), _vertex_pt(p2), _right_pt(p3)
{
    if (p1 == p3)
    {
        _left_pt = p2;
        _right_pt = p4;
        _vertex_pt = p1;
    }
    else if (p1 == p4)
    {
        _left_pt = p2;
        _right_pt = p3;
        _vertex_pt = p1;
    }
    else if (p2 == p3)
    {
        _left_pt = p1;
        _right_pt = p4;
        _vertex_pt = p2;
    }
    else if (p2 == p4)
    {
        _left_pt = p1;
        _right_pt = p3;
        _vertex_pt = p2;
    }
    else
    {
        throw runtime_error("Error: Invalid points.");
    }
}

bool Angle::check_nondegen() const
{
    return _left_pt != _right_pt && !_vertex_pt.is_close(_left_pt) && !_vertex_pt.is_close(_right_pt) && !Coll(_left_pt, _vertex_pt, _right_pt).check_numerically();
}

Slope Angle::left_side() const
{
    return Slope(_vertex_pt, _left_pt);
}

Slope Angle::right_side() const
{
    return Slope(_vertex_pt, _right_pt);
}

double Angle::dot_product() const
{
    return ((_left_pt.x() - _vertex_pt.x()) * (_right_pt.x() - _vertex_pt.x())) +
           ((_left_pt.y() - _vertex_pt.y()) * (_right_pt.y() - _vertex_pt.y()));
}

double Angle::angle() const
{    
    double dx1 = _left_pt.x() - _vertex_pt.x();
    double dy1 = _left_pt.y() - _vertex_pt.y();
    double dx2 = _right_pt.x() - _vertex_pt.x();
    double dy2 = _right_pt.y() - _vertex_pt.y();

    double dot   = dx1 * dx2 + dy1 * dy2;
    double cross = dx1 * dy2 - dy1 * dx2;

    double ang = std::atan2(cross, dot);
    if (ang < 0.0) {
        ang += M_PI;
    }
    if (std::abs(cross) < 1e-14 && std::abs(dot) < 1e-14) {
        return 0.0;
    }

    return ang;
}

std::ostream &operator<<(std::ostream &os, const Angle &angle)
{
    os << "∠(" << angle.left() << " " << angle.vertex() << " " << angle.right() << ")";
    return os;
}

bool Angle::operator==(const Angle &other) const
{
    return _left_pt == other._left_pt && _vertex_pt == other._vertex_pt && _right_pt == other._right_pt;
}

bool Angle::operator!=(const Angle &other) const
{
    return !(*this == other);
}

bool Angle::operator<(const Angle &other) const
{
    if (_left_pt == other._left_pt)
    {
        if (_vertex_pt == other._vertex_pt)
        {
            return _right_pt < other._right_pt;
        }
        return _vertex_pt < other._vertex_pt;
    }
    return _left_pt < other._left_pt;
}