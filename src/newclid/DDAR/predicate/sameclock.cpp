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
    return _left.check_nondegen() && _right.check_nondegen() && (_left.area() > 0) == (_right.area() > 0);
}

bool SameClock::check_equations() const
{
    return true;
}

unique_ptr<Statement> SameClock::normalize() const
{
    return make_unique<SameClock>(*this);
}

ostream &SameClock::print(ostream &os) const
{
    return os << "sameclock " << _left.a() << " " << _left.b() << " " << _left.c() << " " << _right.a() << " " << _right.b() << " " << _right.c();
}