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

vector<unique_ptr<Equation<Slope>>> Perp::as_equation_slope() const
{
    vector<unique_ptr<Equation<Slope>>> result;
    result.push_back(make_unique<Equation<Slope>>(Equation<Slope>::sub_eq_const(_left, _right, Rational(0.5))));
    return result;
}

vector<unique_ptr<Equation<Product>>> Perp::as_equation_product() const
{
    LinearCombination<Product> l(Product(vector<Dist>{_left.dist(), _left.dist()}));
    LinearCombination<Product> r(Product(vector<Dist>{_right.dist(), _right.dist()}));

    vector<unique_ptr<Equation<Product>>> result;
    if (_left.left() == _right.left())
    {
        Dist x = Dist(_left.left(), _right.left());
        LinearCombination<Product> h(Product(vector<Dist>{x, x}));
        result.push_back(make_unique<Equation<Product>>(l + r - h == Rational(0)));
    }
    else if (_left.left() == _right.right())
    {
        Dist x = Dist(_left.left(), _right.right());
        LinearCombination<Product> h(Product(vector<Dist>{x, x}));
        result.push_back(make_unique<Equation<Product>>(l + r - h == Rational(0)));
    }
    else if (_left.right() == _right.left())
    {
        Dist x = Dist(_left.right(), _right.left());
        LinearCombination<Product> h(Product(vector<Dist>{x, x}));
        result.push_back(make_unique<Equation<Product>>(l + r - h == Rational(0)));
    }
    else if (_left.right() == _right.right())
    {
        Dist x = Dist(_left.right(), _right.right());
        LinearCombination<Product> h(Product(vector<Dist>{x, x}));
        result.push_back(make_unique<Equation<Product>>(l + r - h == Rational(0)));
    }
    return result;
}