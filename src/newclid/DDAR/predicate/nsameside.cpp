#include "predicate/nsameside.hpp"
#include "predicate/coll.hpp"
#include "typedef.hpp"
#include <iostream>

using namespace std;

NSameSide::NSameSide(const Point &a, const Point &b, const Point &c, const Point &d, const Point &e, const Point &f)
    : _a(a), _b(b), _c(c), _d(d), _e(e), _f(f) {}

NSameSide::NSameSide(const Coll &left, const Coll &right)
    : _a(left.a()), _b(left.b()), _c(left.c()), _d(right.a()), _e(right.b()), _f(right.c()) {}

NSameSide::NSameSide(const vector<statement_arg> &args)
    : _a(args[0].point), _b(args[1].point), _c(args[2].point), _d(args[3].point), _e(args[4].point), _f(args[5].point) {}

string NSameSide::name() const
{
    return "nsameside";
}

vector<Point> NSameSide::points() const
{
    return {_a, _b, _c, _d, _e, _f};
}

unique_ptr<Statement> NSameSide::normalize() const
{
    return clone();
}

bool NSameSide::check_nondegen() const
{
    return !_a.is_close(_b) && !_b.is_close(_c) && !_c.is_close(_a) &&
           !_d.is_close(_e) && !_e.is_close(_f) && !_f.is_close(_d) &&
           (((_b.x() - _a.x()) * (_c.x() - _a.x()) + (_b.y() - _a.y()) * (_c.y() - _a.y()) > 0) !=
            ((_e.x() - _d.x()) * (_f.x() - _d.x()) + (_e.y() - _d.y()) * (_f.y() - _d.y()) > 0));
}

bool NSameSide::check_equations() const
{
    return true;
}

vector<statement_arg> NSameSide::args() const
{
    return {_a, _b, _c, _d, _e, _f};
}

unique_ptr<Statement> NSameSide::clone() const
{
    return make_unique<NSameSide>(*this);
}

ostream &NSameSide::print(ostream &os) const
{
    return os << _a << " on the other side of [" << _b << ", " << _c << "] as " << _d << " of [" << _e << ", " << _f << "]";
}