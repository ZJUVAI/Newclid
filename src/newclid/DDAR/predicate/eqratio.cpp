#include "predicate/eqratio.hpp"
#include "typedef.hpp"
#include "type/dist.hpp"
#include "type/distlog.hpp"
#include <algorithm>
#include <iostream>

using namespace std;

EqRatio::EqRatio(Dist left_up, Dist left_down, Dist right_up, Dist right_down) : _left_up(left_up), _left_down(left_down), _right_up(right_up), _right_down(right_down)
{
}

string EqRatio::name() const
{
    return "eqratio";
}

vector<Point> EqRatio::points() const
{
    return {_left_up.left(), _left_up.right(), _left_down.left(), _left_down.right(), _right_up.left(), _right_up.right(), _right_down.left(), _right_down.right()};
}

unique_ptr<Statement> EqRatio::clone() const
{
    return make_unique<EqRatio>(*this);
}

bool EqRatio::check_nondegen() const
{
    return !_left_up.left().is_close(_left_up.right()) &&
           !_left_down.left().is_close(_left_down.right()) &&
           !_right_up.left().is_close(_right_up.right()) &&
           !_right_down.left().is_close(_right_down.right());
}

bool EqRatio::check_equations() const
{
    return Numerical::close_enough(_left_up.to_double() * _right_down.to_double(), _left_down.to_double() * _right_up.to_double());
}

vector<statement_arg> EqRatio::args() const
{
    return {_left_up, _left_down, _right_up, _right_down};
}

unique_ptr<Statement> EqRatio::normalize() const
{
    Dist a = left_up().normalize();
    Dist b = left_down().normalize();
    Dist c = right_up().normalize();
    Dist d = right_down().normalize();

    if (min(a, b) > min(c, d))
    {
        swap(a, c);
        swap(b, d);
    }

    if (a > b)
    {
        swap(a, b);
        swap(c, d);
    }

    if (a == b && c > d)
    {
        swap(c, d);
    }

    if (b > c)
    {
        swap(b, c);
    }

    return make_unique<EqRatio>(a, b, c, d);
}

ostream &EqRatio::print(ostream &os) const
{
    return os << _left_up << ":" << _left_down << " = " << _right_up << ":" << _right_down;
}

vector<unique_ptr<Equation>> EqRatio::as_equation_dist(bool exp, ObjectTable *table) const
{
    vector<unique_ptr<Equation>> result;
    if (exp)
    {
        result.push_back(make_unique<Equation>(Equation({Term({_left_up, _right_down}, table), -Term({_left_down, _right_up}, table)}, table)));
    }
    return result;
}

vector<unique_ptr<Equation>> EqRatio::as_equation_distlog(bool exp, ObjectTable *table) const
{
    vector<unique_ptr<Equation>> result;
    result.push_back(make_unique<Equation>(Equation({Term(DistLog(_left_up), table), Term(DistLog(_right_down), table), -Term(DistLog(_left_down), table), -Term(DistLog(_right_up), table)}, table)));
    return result;
}