#include "predicate/npara.hpp"
#include "predicate/para.hpp"
#include "type/slope.hpp"
#include <iostream>

using namespace std;

NPara::NPara(const Slope &left, const Slope &right) : _left(left), _right(right) {}

string NPara::name() const
{
    return "npara";
}

vector<Point> NPara::points() const
{
    return {_left.left(), _left.right(), _right.left(), _right.right()};
}

unique_ptr<Statement> NPara::normalize() const
{
    return make_unique<NPara>(min(_left, _right), max(_left, _right));
}

unique_ptr<Statement> NPara::replace(Point p, Point q) const
{
    auto left_pts = _left.points();
    Point la = left_pts[0], lb = left_pts[1];

    Point new_la = (la == p) ? q : la;
    Point new_lb = (lb == p) ? q : lb;

    Slope new_left(new_la, new_lb);

    auto right_pts = _right.points();
    Point ra = right_pts[0], rb = right_pts[1];

    Point new_ra = (ra == p) ? q : ra;
    Point new_rb = (rb == p) ? q : rb;

    Slope new_right(new_ra, new_rb);

    return make_unique<NPara>(new_left, new_right);
}

bool NPara::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen() && !Para(_left, _right).check_equations();
}

bool NPara::check_equations() const
{
    return true;
}

vector<statement_arg> NPara::args() const
{
    return {_left, _right};
}

unique_ptr<Statement> NPara::clone() const
{
    return make_unique<NPara>(*this);
}

ostream &NPara::print(ostream &os) const
{
    return os << _left.left() << _left.right() << "∦" << _right.left() << _right.right();
}