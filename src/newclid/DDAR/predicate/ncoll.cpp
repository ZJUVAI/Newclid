#include "predicate/ncoll.hpp"
#include "predicate/coll.hpp"
#include <iostream>

using namespace std;

NColl::NColl(Point a, Point b, Point c) : _a(a), _b(b), _c(c) {}

string NColl::name() const
{
    return "ncoll";
}

vector<Point> NColl::points() const
{
    return {_a, _b, _c};
}

unique_ptr<Statement> NColl::normalize() const
{
    vector<Point> points = {_a, _b, _c};
    sort(points.begin(), points.end());
    return make_unique<NColl>(points[0], points[1], points[2]);
}

bool NColl::check_nondegen() const
{
    return !_a.is_close(_b) && !_b.is_close(_c) && !_c.is_close(_a) && !Coll(_a, _b, _c).check_equations();
}

bool NColl::check_equations() const
{
    return true;
}

vector<statement_arg> NColl::args() const
{
    return {_a, _b, _c};
}

unique_ptr<Statement> NColl::clone() const
{
    return make_unique<NColl>(*this);
}

ostream &NColl::print(ostream &os) const
{
    return os << _a << " ∉ " << _b << _c;
}