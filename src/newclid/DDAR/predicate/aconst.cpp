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

vector<unique_ptr<Equation>> AConst::as_equation(bool log, bool exp) const
{
    vector<unique_ptr<Equation>> result;
    result.push_back(make_unique<Equation>(Equation({Term(_angle.right_side()), -Term(_angle.left_side()), -Term(Pi(), _rhs)})));
    return result;
}

vector<string> AConst::to_tokens() const
{
    vector<string> tokens = {"aconst"};
    tokens.push_back(_angle.left().name());
    tokens.push_back(_angle.vertex().name());
    tokens.push_back(_angle.vertex().name());
    tokens.push_back(_angle.right().name());
    tokens.push_back(std::to_string(_rhs.numerator()) + "pi/" + std::to_string(_rhs.denominator()));
    return tokens;
}