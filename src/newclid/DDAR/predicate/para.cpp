#include "predicate/para.hpp"
#include "type/slope.hpp"
#include "ar/equation.hpp"
#include "typedef.hpp"
#include <iostream>

using namespace std;

Para::Para(Slope left, Slope right) : _left(left), _right(right) {}

string Para::name() const
{
    return "para";
}

vector<Point> Para::points() const
{
    return {_left.left(), _left.right(), _right.left(), _right.right()};
}

unique_ptr<Statement> Para::normalize() const
{
    if (_left > _right)
    {
        return make_unique<Para>(_right, _left);
    }
    return make_unique<Para>(*this);
}

bool Para::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool Para::check_equations() const
{
    return Numerical::close_enough(_left.angle(), _right.angle());
}

vector<statement_arg> Para::args() const
{
    return {_left, _right};
}

unique_ptr<Statement> Para::clone() const
{
    return make_unique<Para>(_left, _right);
}

ostream &Para::print(ostream &os) const
{
    return os << _left.left() << _left.right() << " ∥ " << _right.left() << _right.right();
}

vector<unique_ptr<Equation<Slope>>> Para::as_equation_slope() const
{
    vector<unique_ptr<Equation<Slope>>> result;
    result.push_back(make_unique<Equation<Slope>>(Equation<Slope>::sub_eq_const(_left, _right, Rational((long long)0))));
    return result;
}