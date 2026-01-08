#include "predicate/orthocenter.hpp"

using namespace std;

OrthoCenter::OrthoCenter(const Point &center, const Triangle &triangle) : _center(center), _triangle(triangle)
{
}

OrthoCenter::OrthoCenter(const vector<statement_arg> &args) : _center(args[0].point), _triangle(args[1].tri) {}

string OrthoCenter::name() const
{
    return "orthocenter";
}

vector<Point> OrthoCenter::points() const
{
    return {_triangle.a(), _triangle.b(), _triangle.c(), _center};
}

unique_ptr<Statement> OrthoCenter::replace(Point p, Point q) const
{
    Point new_center = (_center == p) ? q : _center;

    auto pts = _triangle.points();
    Point a = pts[0], b = pts[1], c = pts[2];

    Point new_a = (a == p) ? q : a;
    Point new_b = (b == p) ? q : b;
    Point new_c = (c == p) ? q : c;

    Triangle new_triangle(new_a, new_b, new_c);

    return make_unique<OrthoCenter>(new_center, new_triangle);
}

unique_ptr<Statement> OrthoCenter::clone() const
{
    return make_unique<OrthoCenter>(*this);
}

bool OrthoCenter::check_nondegen() const
{
    return _triangle.check_nondegen() && perp_a().check_nondegen() && perp_b().check_nondegen() && perp_c().check_nondegen();
}

bool OrthoCenter::check_equations() const
{
    return perp_a().check_equations() && perp_b().check_equations();
}

vector<statement_arg> OrthoCenter::args() const
{
    return {_center, _triangle};
}

unique_ptr<Statement> OrthoCenter::normalize() const
{
    return make_unique<OrthoCenter>(_center, _triangle.normalize());
}

ostream &OrthoCenter::print(ostream &os) const
{
    return os << _center << " is the orthocenter of " << _triangle;
}

Perp OrthoCenter::perp_a() const
{
    return Perp(Slope(_triangle.a(), _center), Slope(_triangle.b(), _triangle.c()));
}

Perp OrthoCenter::perp_b() const
{
    return Perp(Slope(_triangle.b(), _center), Slope(_triangle.c(), _triangle.a()));
}

Perp OrthoCenter::perp_c() const
{
    return Perp(Slope(_triangle.c(), _center), Slope(_triangle.a(), _triangle.b()));
}

vector<OrthoCenter> OrthoCenter::cyclic_rotations() const
{
    vector<OrthoCenter> res;
    res.reserve(3);
    for (const auto &tri : _triangle.cyclic_rotations())
    {
        res.push_back(OrthoCenter(_center, tri));
    }
    return res;
}