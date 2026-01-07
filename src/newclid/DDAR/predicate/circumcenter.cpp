#include "predicate/circumcenter.hpp"
#include "predicate/cong.hpp"
#include "typedef.hpp"
#include <ostream>
#include <string>
#include <vector>
using namespace std;

CircumCenter::CircumCenter(Point center, Triangle triangle) : _center(center), _triangle(triangle)
{
}

CircumCenter::CircumCenter(const vector<statement_arg> &args) : _center(args[0].point), _triangle(args[1].tri)
{
}

string CircumCenter::name() const
{
    return "circle";
}

vector<Point> CircumCenter::points() const
{
    return {_center, _triangle.a(), _triangle.b(), _triangle.c()};
}

bool CircumCenter::check_nondegen() const
{
    return _triangle.check_nondegen();
}

bool CircumCenter::check_equations() const
{
    return cong_ab().check_equations() && cong_bc().check_equations();
}

vector<statement_arg> CircumCenter::args() const
{
    return {_center, _triangle};
}

unique_ptr<Statement> CircumCenter::clone() const
{
    return make_unique<CircumCenter>(*this);
}

Cong CircumCenter::cong_ab() const
{
    return Cong(Dist(center(), a()), Dist(center(), b()));
}

Cong CircumCenter::cong_bc() const
{
    return Cong(Dist(center(), b()), Dist(center(), c()));
}

Cong CircumCenter::cong_ac() const
{
    return Cong(Dist(center(), a()), Dist(center(), c()));
}

ostream &CircumCenter::print(ostream &os) const
{
    return os << center().name() << " = circumcenter(▵" << a().name() << " " << b().name() << " " << c().name() << ")";
}

unique_ptr<Statement> CircumCenter::normalize() const
{
    return make_unique<CircumCenter>(_center, _triangle.normalize());
}

unique_ptr<Statement> CircumCenter::replace(Point p, Point q) const
{
    Point new_center = (_center == p) ? q : _center;
    auto pts = _triangle.points();
    Point a = pts[0], b = pts[1], c = pts[2];
    Point new_a = (a == p) ? q : a;
    Point new_b = (b == p) ? q : b;
    Point new_c = (c == p) ? q : c;
    Triangle new_triangle(new_a, new_b, new_c);
    return make_unique<CircumCenter>(new_center, new_triangle);
}