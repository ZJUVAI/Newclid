#include "type/triangle.hpp"
#include "type/point.hpp"
#include "type/angle.hpp"
#include "type/dist.hpp"
#include "predicate/coll.hpp"
#include <iostream>
#include <vector>

using namespace std;

Triangle::Triangle(Point a, Point b, Point c) : _a(a), _b(b), _c(c) {}

double Triangle::area() const
{
    return 0.5 * ((_c.y() - _a.y()) * (_b.x() - _a.x()) - (_c.x() - _a.x()) * (_b.y() - _a.y()));
}

Angle Triangle::angle_a() const
{
    return Angle(_c, _a, _b);
}

Angle Triangle::angle_b() const
{
    return Angle(_a, _b, _c);
}

Angle Triangle::angle_c() const
{
    return Angle(_b, _c, _a);
}

Dist Triangle::dist_ab() const
{
    return Dist(_a, _b);
}

Dist Triangle::dist_bc() const
{
    return Dist(_b, _c);
}

Dist Triangle::dist_ac() const
{
    return Dist(_a, _c);
}

Point Triangle::operator[](size_t ind) const
{
    switch (ind % 3)
    {
    case 0:
        return _a;
    case 1:
        return _b;
    case 2:
        return _c;
    default:
        throw runtime_error("Invalid index");
    }
}

vector<Triangle> Triangle::cyclic_rotations() const
{
    vector<Triangle> res;
    res.reserve(3);
    res.push_back(*this);
    res.push_back(Triangle(_c, _a, _b));
    res.push_back(Triangle(_b, _c, _a));
    return res;
}

vector<Triangle> Triangle::permutations() const
{
    vector<Triangle> res;
    res.reserve(6);
    res.push_back(*this);
    res.push_back(Triangle(_b, _c, _a));
    res.push_back(Triangle(_c, _a, _b));
    res.push_back(Triangle(_a, _c, _b));
    res.push_back(Triangle(_c, _b, _a));
    res.push_back(Triangle(_b, _a, _c));
    return res;
}

vector<Dist> Triangle::dists() const
{
    vector<Dist> res;
    res.reserve(3);
    res.push_back(dist_ab());
    res.push_back(dist_bc());
    res.push_back(dist_ac());
    return res;
}

vector<Angle> Triangle::angles() const
{
    vector<Angle> res;
    res.reserve(3);
    res.push_back(angle_a());
    res.push_back(angle_b());
    res.push_back(angle_c());
    return res;
}

bool Triangle::check_nondegen() const
{
    return !Coll(_a, _b, _c).check_numerically();
}

bool Triangle::overlap(Triangle const &other) const
{
    return _a.is_close(other._a) && _b.is_close(other._b) && _c.is_close(other._c);
}

ostream &operator<<(ostream &os, const Triangle &triangle)
{
    os << "▵" << triangle.a() << " " << triangle.b() << " " << triangle.c();
    return os;
}

Triangle Triangle::normalize() const
{
    vector<Point> pts = {_a, _b, _c};
    sort(pts.begin(), pts.end());
    return Triangle(pts[0], pts[1], pts[2]);
}

bool Triangle::operator==(const Triangle &other) const
{
    return _a == other._a && _b == other._b && _c == other._c;
}

bool Triangle::operator<(const Triangle &other) const
{
    if (_a == other._a)
    {
        if (_b == other._b)
        {
            return _c < other._c;
        }
        return _b < other._b;
    }
    return _a < other._a;
}