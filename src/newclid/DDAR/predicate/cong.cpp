#include "predicate/cong.hpp"
#include "type/dist.hpp"
#include "type/rational.hpp"
#include "type/product.hpp"
#include "ar/linear_combination.hpp"
#include "ar/equation.hpp"
#include <iostream>
#include <vector>
#include <optional>

using namespace std;

string Cong::name() const
{
    return "cong";
}

vector<Point> Cong::points() const
{
    return {_left.left(), _left.right(), _right.left(), _right.right()};
}

unique_ptr<Statement> Cong::normalize() const
{
    if (_left > _right)
    {
        return make_unique<Cong>(_right.normalize(), _left.normalize());
    }
    return make_unique<Cong>(_left.normalize(), _right.normalize());
}

bool Cong::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool Cong::check_equations() const
{
    return Numerical::close_enough(_left.to_double(), _right.to_double());
}

vector<statement_arg> Cong::args() const
{
    return {_left, _right};
}

ostream &Cong::print(ostream &os) const
{
    return os << _left << " = " << _right;
}

vector<unique_ptr<Equation<DistLog>>> Cong::as_equation_distlog() const
{
    vector<unique_ptr<Equation<DistLog>>> result;
    result.push_back(make_unique<Equation<DistLog>>(LinearCombination<DistLog>(_left) - LinearCombination<DistLog>(_right) == Rational((long long)0)));
    return result;
}

vector<unique_ptr<Equation<Product>>> Cong::as_equation_product() const
{
    vector<unique_ptr<Equation<Product>>> result;
    result.push_back(make_unique<Equation<Product>>(LinearCombination<Product>(_left) - LinearCombination<Product>(_right) == Rational((long long)0)));
    return result;
}