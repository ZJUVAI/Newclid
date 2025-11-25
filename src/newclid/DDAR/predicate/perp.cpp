#include "predicate/perp.hpp"
#include "ar/equation.hpp"

using namespace std;

Perp::Perp(Slope left, Slope right) : _left(left), _right(right) {}

string Perp::name() const
{
    return "perp";
}

vector<Point> Perp::points() const
{
    return {_left.left(), _left.right(), _right.left(), _right.right()};
}

unique_ptr<Statement> Perp::normalize() const
{
    if (_left > _right)
    {
        return make_unique<Perp>(_right, _left);
    }
    return make_unique<Perp>(*this);
}

bool Perp::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool Perp::check_equations() const
{
    return Numerical::close_enough((_left.right().x() - _left.left().x()) * (_right.right().x() - _right.left().x()),
                                   -(_left.right().y() - _left.left().y()) * (_right.right().y() - _right.left().y()));
}

vector<statement_arg> Perp::args() const
{
    return {_left, _right};
}

unique_ptr<Statement> Perp::clone() const
{
    return make_unique<Perp>(_left, _right);
}

ostream &Perp::print(ostream &os) const
{
    return os << _left.left() << _left.right() << " ⟂  " << _right.left() << _right.right();
}

vector<unique_ptr<Equation>> Perp::as_equation() const
{
    vector<unique_ptr<Equation>> result;
    result.push_back(make_unique<Equation>(Equation({Term(_left), -Term(_right), -Term(Pi(), Rational(0.5))})));
    Term l({_left.dist(), _left.dist()});
    Term r({_right.dist(), _right.dist()});

    if (_left.left() == _right.left())
    {
        Dist x = Dist(_left.right(), _right.right());
        Term h({x, x});
        result.push_back(make_unique<Equation>(Equation({l, r, -h})));
    }
    else if (_left.left() == _right.right())
    {
        Dist x = Dist(_left.right(), _right.left());
        Term h({x, x});
        result.push_back(make_unique<Equation>(Equation({l, r, -h})));
    }
    else if (_left.right() == _right.left())
    {
        Dist x = Dist(_left.left(), _right.right());
        Term h({x, x});
        result.push_back(make_unique<Equation>(Equation({l, r, -h})));
    }
    else if (_left.right() == _right.right())
    {
        Dist x = Dist(_left.left(), _right.left());
        Term h({x, x});
        result.push_back(make_unique<Equation>(Equation({l, r, -h})));
    }
    return result;
}
