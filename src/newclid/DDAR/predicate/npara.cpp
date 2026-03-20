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