#include "predicate/sameside.hpp"
#include <iostream>

using namespace std;

SameSide::SameSide(const Point &a, const Point &b, const Point &c, const Point &d, const Point &e, const Point &f)
    : _a(a), _b(b), _c(c), _d(d), _e(e), _f(f) {}

SameSide::SameSide(const Coll &left, const Coll &right)
    : _a(left.a()), _b(left.b()), _c(left.c()), _d(right.a()), _e(right.b()), _f(right.c()) {}

SameSide::SameSide(const std::vector<statement_arg> &args)
    : _a(args[0].point), _b(args[1].point), _c(args[2].point), _d(args[3].point), _e(args[4].point), _f(args[5].point) {}

std::string SameSide::name() const
{
    return "sameside";
}

std::vector<Point> SameSide::points() const
{
    return {_a, _b, _c, _d, _e, _f};
}

std::unique_ptr<Statement> SameSide::normalize() const
{
    return clone();
}

bool SameSide::check_nondegen() const
{
    return !_a.is_close(_b) && !_b.is_close(_c) && !_c.is_close(_a) &&
           !_d.is_close(_e) && !_e.is_close(_f) && !_f.is_close(_d) &&
           (((_b.x() - _a.x()) * (_c.x() - _a.x()) + (_b.y() - _a.y()) * (_c.y() - _a.y()) > 0) ==
            ((_e.x() - _d.x()) * (_f.x() - _d.x()) + (_e.y() - _d.y()) * (_f.y() - _d.y()) > 0));
}

bool SameSide::check_equations() const
{
    return true;
}

std::vector<statement_arg> SameSide::args() const
{
    return {_a, _b, _c, _d, _e, _f};
}

std::unique_ptr<Statement> SameSide::clone() const
{
    return make_unique<SameSide>(*this);
}

std::ostream &SameSide::print(std::ostream &os) const
{
    return os << _a << " on the same side of [" << _b << ", " << _c << "] as " << _d << " of [" << _e << ", " << _f << "]";
}

unique_ptr<Statement> SameSide::replace(Point p, Point q) const
{
    Point new_a = (_a == p) ? q : _a;
    Point new_b = (_b == p) ? q : _b;
    Point new_c = (_c == p) ? q : _c;
    Point new_d = (_d == p) ? q : _d;
    Point new_e = (_e == p) ? q : _e;
    Point new_f = (_f == p) ? q : _f;

    return make_unique<SameSide>(new_a, new_b, new_c, new_d, new_e, new_f);
}