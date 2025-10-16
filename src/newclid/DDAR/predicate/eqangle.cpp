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

Equation<Slope> *EqAngle::as_equation_slope() const
{
    return new Equation<Slope>(Equation<Slope>::sub_eq_sub(_left.left_side(), _left.right_side(), _right.left_side(), _right.right_side()));
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