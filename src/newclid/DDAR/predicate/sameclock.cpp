#include "predicate/sameclock.hpp"
#include <vector>
#include <iostream>

using namespace std;

SameClock::SameClock(const Triangle &left, const Triangle &right) : _left(left), _right(right) {}

string SameClock::name() const { return "sameclock"; }

vector<Point> SameClock::points() const
{
    return {_left.a(), _left.b(), _left.c(), _right.a(), _right.b(), _right.c()};
}

vector<statement_arg> SameClock::args() const
{
    return {_left, _right};
}

unique_ptr<Statement> SameClock::clone() const
{
    return make_unique<SameClock>(*this);
}

bool SameClock::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool SameClock::check_equations() const
{
    return (_left.area() > 0) == (_right.area() > 0);
}

unique_ptr<Statement> SameClock::normalize() const
{
    return make_unique<SameClock>(*this);
}

ostream &SameClock::print(ostream &os) const
{
    return os << "sameclock " << _left.a() << " " << _left.b() << " " << _left.c() << " " << _right.a() << " " << _right.b() << " " << _right.c();
}

unique_ptr<Statement> SameClock::replace(Point p, Point q) const
{
    auto left_pts = _left.points();
    Point la = left_pts[0], lb = left_pts[1], lc = left_pts[2];

    Point new_la = (la == p) ? q : la;
    Point new_lb = (lb == p) ? q : lb;
    Point new_lc = (lc == p) ? q : lc;

    Triangle new_left(new_la, new_lb, new_lc);

    auto right_pts = _right.points();
    Point ra = right_pts[0], rb = right_pts[1], rc = right_pts[2];

    Point new_ra = (ra == p) ? q : ra;
    Point new_rb = (rb == p) ? q : rb;
    Point new_rc = (rc == p) ? q : rc;

    Triangle new_right(new_ra, new_rb, new_rc);

    return make_unique<SameClock>(new_left, new_right);
}