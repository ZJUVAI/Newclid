#include "predicate/thales.hpp"
#include "predicate/para.hpp"
#include "predicate/coll.hpp"
#include "type/slope.hpp"
#include <algorithm>
#include <iostream>

using namespace std;

Thales::Thales(Coll left, Coll right) : _left(left), _right(right) {}

Thales::Thales(const vector<statement_arg> &args) : _left(Coll(args[0].point, args[1].point, args[2].point)), _right(Coll(args[3].point, args[4].point, args[5].point)) {}

string Thales::name() const
{
    return "thales";
}

vector<Point> Thales::points() const
{
    return {_left.a(), _left.b(), _left.c(), _right.a(), _right.b(), _right.c()};
}

unique_ptr<Statement> Thales::clone() const
{
    return make_unique<Thales>(_left, _right);
}

bool Thales::check_nondegen() const
{
    return para_ab().check_nondegen() &&
           para_ac().check_nondegen() &&
           !Coll(_left.a(), _left.b(), _right.a()).check_equations();
}

bool Thales::check_equations() const
{
    return _left.check_equations() && _right.check_equations() && para_ab().check_equations() && para_bc().check_equations();
}

vector<statement_arg> Thales::args() const
{
    return {_left.a(), _left.b(), _left.c(), _right.a(), _right.b(), _right.c()};
}

unique_ptr<Statement> Thales::normalize() const
{
    auto all = permutations();
    return make_unique<Thales>(*min_element(all.begin(), all.end()));
}

ostream &Thales::print(ostream &os) const
{
    return os << "thales(" << _left << ", " << _right << ")";
}

vector<Thales> Thales::permutations() const
{
    vector<Thales> result;

    auto left_permutations = _left.permutations();
    auto right_permutations = _right.permutations();

    auto left_iter = left_permutations.begin();
    auto right_iter = right_permutations.begin();
    for (; left_iter != left_permutations.end() && right_iter != right_permutations.end(); ++left_iter, ++right_iter)
    {
        result.push_back({*left_iter, *right_iter});
    }

    return result;
}

Para Thales::para_ab() const
{
    return Para(Slope(_left.a(), _right.a()), Slope(_left.b(), _right.b()));
}

Para Thales::para_bc() const
{
    return Para(Slope(_left.b(), _right.b()), Slope(_left.c(), _right.c()));
}

Para Thales::para_ac() const
{
    return Para(Slope(_left.a(), _right.a()), Slope(_left.c(), _right.c()));
}

Thales Thales::rotate() const
{
    return Thales(Coll(_left.b(), _left.c(), _left.a()), Coll(_right.b(), _right.c(), _right.a()));
}

bool Thales::operator==(const Thales &other) const
{
    return _left == other._left && _right == other._right;
}

bool Thales::operator!=(const Thales &other) const
{
    return !(*this == other);
}

bool Thales::operator<(const Thales &other) const
{
    if (_left == other._left)
    {
        return _right < other._right;
    }
    return _left < other._left;
}

bool Thales::operator<=(const Thales &other) const
{
    return *this < other || *this == other;
}

bool Thales::operator>(const Thales &other) const
{
    return !(*this <= other);
}

bool Thales::operator>=(const Thales &other) const
{
    return !(*this < other);
}