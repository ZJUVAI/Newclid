#include "predicate/eqangle.hpp"
#include "type/angle.hpp"
#include "ar/equation.hpp"
#include "typedef.hpp"

using namespace std;

EqAngle::EqAngle(Angle left, Angle right) : _left(left), _right(right)
{
}

EqAngle::EqAngle(Point p1, Point p2, Point p3, Point p4, Point p5, Point p6, Point p7, Point p8) : _left(p1, p2, p3), _right(p5, p6, p7)
{
    bool l = false;
    bool r = false;
    if (p1 == p3)
    {
        _left = Angle(p2, p1, p4);
        l = true;
    }
    else if (p1 == p4)
    {
        _left = Angle(p2, p1, p3);
        l = true;
    }
    else if (p2 == p3)
    {
        _left = Angle(p1, p2, p4);
        l = true;
    }
    else if (p2 == p4)
    {
        _left = Angle(p1, p2, p3);
        l = true;
    }

    if (p5 == p7)
    {
        _right = Angle(p6, p5, p8);
        r = true;
    }
    else if (p5 == p8)
    {
        _right = Angle(p6, p5, p7);
        r = true;
    }
    else if (p6 == p7)
    {
        _right = Angle(p5, p6, p8);
        r = true;
    }
    else if (p6 == p8)
    {
        _right = Angle(p5, p6, p7);
        r = true;
    }

    if (!l || !r)
    {
        l = r = false;
        Point p = p3;
        p3 = p5;
        p5 = p;
        p = p4;
        p4 = p6;
        p6 = p;
        if (p1 == p3)
        {
            _left = Angle(p2, p1, p4);
            l = true;
        }
        else if (p1 == p4)
        {
            _left = Angle(p2, p1, p3);
            l = true;
        }
        else if (p2 == p3)
        {
            _left = Angle(p1, p2, p4);
            l = true;
        }
        else if (p2 == p4)
        {
            _left = Angle(p1, p2, p3);
            l = true;
        }

        if (p5 == p7)
        {
            _right = Angle(p6, p5, p8);
            r = true;
        }
        else if (p5 == p8)
        {
            _right = Angle(p6, p5, p7);
            r = true;
        }
        else if (p6 == p7)
        {
            _right = Angle(p5, p6, p8);
            r = true;
        }
        else if (p6 == p8)
        {
            _right = Angle(p5, p6, p7);
            r = true;
        }
    }
}

string EqAngle::name() const
{
    return "eqangle";
}

vector<Point> EqAngle::points() const
{
    return {_left.left(), _left.vertex(), _left.right(), _right.left(), _right.vertex(), _right.right()};
}

unique_ptr<Statement> EqAngle::clone() const
{
    return make_unique<EqAngle>(*this);
}

bool EqAngle::check_nondegen() const
{
    return _left.check_nondegen() && _right.check_nondegen();
}

bool EqAngle::check_equations() const
{
    return Numerical::close_enough(_left.angle(), _right.angle());
}

vector<statement_arg> EqAngle::args() const
{
    return {_left, _right};
}

unique_ptr<Statement> EqAngle::normalize() const
{
    auto all = permutations();
    return make_unique<EqAngle>(*min_element(all.begin(), all.end()));
}

ostream &EqAngle::print(ostream &os) const
{
    return os << _left << " = " << _right;
}

vector<EqAngle> EqAngle::permutations() const
{
    vector<EqAngle> res;
    res.reserve(4);
    res.emplace_back(*this);
    res.emplace_back(_right, _left);
    res.emplace_back(-_left, -_right);
    res.emplace_back(-_right, -_left);
    return res;
}

vector<unique_ptr<Equation>> EqAngle::as_equation() const
{
    vector<unique_ptr<Equation>> result;
    result.push_back(make_unique<Equation>(Equation({Term(_left.left_side()), -Term(_left.right_side()), -Term(_right.left_side()), Term(_right.right_side())})));
    return result;
}

bool EqAngle::operator==(const EqAngle &other) const
{
    return _left == other._left && _right == other._right;
}

bool EqAngle::operator!=(const EqAngle &other) const
{
    return !(*this == other);
}

bool EqAngle::operator<(const EqAngle &other) const
{
    if (_left == other._left)
        return _right < other._right;
    return _left < other._left;
}

bool EqAngle::operator<=(const EqAngle &other) const
{
    return *this < other || *this == other;
}

bool EqAngle::operator>(const EqAngle &other) const
{
    return !(*this <= other);
}

bool EqAngle::operator>=(const EqAngle &other) const
{
    return !(*this < other);
}

string EqAngle::to_string() const
{
    string res = name();
    res += " " + _left.left().name();
    res += " " + _left.vertex().name();
    res += " " + _left.vertex().name();
    res += " " + _left.right().name();
    res += " " + _right.left().name();
    res += " " + _right.vertex().name();
    res += " " + _right.vertex().name();
    res += " " + _right.right().name();
    return res;
}

vector<string> EqAngle::to_tokens() const
{
    vector<string> tokens = {"eqangle"};
    tokens.push_back(_left.left().name());
    tokens.push_back(_left.vertex().name());
    tokens.push_back(_left.vertex().name());
    tokens.push_back(_left.right().name());
    tokens.push_back(_right.left().name());
    tokens.push_back(_right.vertex().name());
    tokens.push_back(_right.vertex().name());
    tokens.push_back(_right.right().name());
    return tokens;
}