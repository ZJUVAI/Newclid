#include "predicate/aconst.hpp"
#include "predicate/statement.hpp"
#include "type/angle.hpp"
#include <algorithm>
#include <array>
#include <memory>
#include <optional>
#include <ostream>
#include <string>
#include <vector>

using namespace std;

AConst::AConst(const Angle &ang, const Rational &rhs) : _angle(ang), _rhs(rhs)
{
}

string AConst::name() const
{
    return "aconst";
}

vector<Point> AConst::points() const
{
    return _angle.points();
}

unique_ptr<Statement> AConst::normalize() const
{
    if (_angle.left() < _angle.right())
    {
        return clone();
    }
    return make_unique<AConst>(-_angle, -_rhs);
}

bool AConst::check_nondegen() const
{
    return _angle.check_nondegen();
}

bool AConst::check_equations() const
{
    return Numerical::close_enough(_angle.angle(), _rhs.to_double());
}

vector<statement_arg> AConst::args() const
{
    return {_angle, _rhs};
}

ostream &AConst::print(std::ostream &out) const
{
    return out << _angle << " = " << _rhs << "π";
}

Equation<Slope> *AConst::as_equation_slope() const
{
    return new Equation<Slope>(Equation<Slope>::sub_eq_const(_angle.right_side(), _angle.left_side(), _rhs));
}

vector<string> AConst::to_tokens() const
{
    vector<string> tokens = {"aconst"};
    for (const auto &pt : points())
    {
        tokens.push_back(pt.name());
    }
    tokens.push_back(_rhs.to_string() + "pi");
    return tokens;
}