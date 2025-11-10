#include "predicate/rconst.hpp"
#include "type/rational.hpp"
#include "type/dist.hpp"
#include "ar/equation.hpp"
#include <cmath>

using namespace std;

RConst::RConst(const Dist &left, const Dist &right, const Rational &ratio) : _left(left), _right(right), _ratio(ratio) {}

string RConst::name() const { return "rconst"; }

vector<Point> RConst::points() const { return {_left.left(), _left.right(), _right.left(), _right.right()}; }

unique_ptr<Statement> RConst::clone() const
{
    return make_unique<RConst>(_left, _right, _ratio);
}

unique_ptr<Statement> RConst::normalize() const
{
    if (_left < _right)
    {
        return make_unique<RConst>(_left, _right, _ratio);
    }
    return make_unique<RConst>(swap());
}

bool RConst::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool RConst::check_equations() const
{
    return Numerical::close_enough(_left.to_double(), _right.to_double() * _ratio.to_double());
}

vector<statement_arg> RConst::args() const
{
    return {_left, _right, _ratio};
}

RConst RConst::swap() const
{
    return RConst(_right, _left, Rational(1.0) / _ratio);
}

ostream &RConst::print(ostream &os) const
{
    return os << _left << ":" << _right << " = " << _ratio;
}

vector<Equation<DistLog> *> RConst::as_equation_distlog() const
{
    return {new Equation<DistLog>(LinearCombination<DistLog>(_left) - LinearCombination<DistLog>(_right) == Rational(log(_ratio.to_double())))};
}

vector<Equation<Product> *> RConst::as_equation_product() const
{
    return {new Equation<Product>(LinearCombination<Product>(_left) - LinearCombination<Product>(_right, _ratio) == Rational((long long)0))};
}

string RConst::to_string() const
{
    string res = name();
    for (const auto &pt : points())
    {
        res += " " + pt.name();
    }
    res += " " + _ratio.to_string();
    return res;
}

vector<string> RConst::to_tokens() const
{
    vector<string> res = {"rconst"};
    for (const auto &pt : points())
    {
        res.push_back(pt.name());
    }
    res.push_back(_ratio.to_string());
    return res;
}