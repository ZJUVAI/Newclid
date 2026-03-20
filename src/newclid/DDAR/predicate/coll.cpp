#include "predicate/coll.hpp"
#include "predicate/eqratio.hpp"
#include "type/point.hpp"
#include "type/dist.hpp"
#include <iostream>
#include <vector>

using namespace std;

Coll::Coll(Point a, Point b, Point c) : _a(a), _b(b), _c(c) {}

Coll::Coll(const vector<statement_arg> &args) : _a(args[0].point), _b(args[1].point), _c(args[2].point) {}

string Coll::name() const
{
    return "coll";
}

vector<Point> Coll::points() const
{
    return {_a, _b, _c};
}

unique_ptr<Statement> Coll::normalize() const
{
    vector<Point> pts = points();
    sort(pts.begin(), pts.end());
    return make_unique<Coll>(pts[0], pts[1], pts[2]);
}

vector<statement_arg> Coll::args() const
{
    return {_a, _b, _c};
}

bool Coll::check_nondegen() const
{
    return !_a.is_close(_b) && !_a.is_close(_c) && !_b.is_close(_c);
}

bool Coll::check_equations() const
{
    double const lhs = ((_b.x() - _a.x()) * (_c.y() - _a.y()));
    double const rhs = ((_c.x() - _a.x()) * (_b.y() - _a.y()));
    return Numerical::close_enough(lhs, rhs);
}

vector<Coll> Coll::cyclic_rotations() const
{
    vector<Coll> res;
    res.reserve(3);
    res.push_back(Coll(_a, _b, _c));
    res.push_back(Coll(_b, _c, _a));
    res.push_back(Coll(_c, _a, _b));
    return res;
}

vector<Coll> Coll::permutations() const
{
    vector<Coll> res;
    res.reserve(6);
    res.push_back(Coll(_a, _b, _c));
    res.push_back(Coll(_a, _c, _b));
    res.push_back(Coll(_b, _a, _c));
    res.push_back(Coll(_b, _c, _a));
    res.push_back(Coll(_c, _a, _b));
    res.push_back(Coll(_c, _b, _a));
    return res;
}

bool Coll::is_between() const
{
    // 判断三点是否共线
    double cross = (_b.y() - _a.y()) * (_c.x() - _a.x()) - (_b.x() - _a.x()) * (_c.y() - _a.y());
    if (fabs(cross) > 1e-9) // 不共线
        return false;

    // 判断b是否在a和c之间（不包含端点）
    double dot = (_b.x() - _a.x()) * (_c.x() - _a.x()) + (_b.y() - _a.y()) * (_c.y() - _a.y());
    if (dot <= 0)
        return false;

    double len_sq = (_c.x() - _a.x()) * (_c.x() - _a.x()) + (_c.y() - _a.y()) * (_c.y() - _a.y());
    if (dot >= len_sq)
        return false;

    return true;
}

EqRatio Coll::eqratio_ab_bc(const Coll &other) const
{
    return EqRatio(Dist(_a, _b), Dist(_b, _c), Dist(other.a(), other.b()), Dist(other.b(), other.c()));
}

EqRatio Coll::eqratio_ab_ac(const Coll &other) const
{
    return EqRatio(Dist(_a, _b), Dist(_a, _c), Dist(other.a(), other.b()), Dist(other.a(), other.c()));
}

ostream &Coll::print(ostream &out) const
{
    return out << _a << " ∈ " << _b << _c;
}

bool Coll::operator==(const Coll &other) const
{
    return _a == other._a && _b == other._b && _c == other._c;
}

bool Coll::operator<(const Coll &other) const
{
    if (_a == other._a)
    {
        if (_b == other._b)
        {
            return _c < other._c;
        }
        return _b < other._b;
    }
    return _a < other._a;
}

vector<unique_ptr<Equation>> Coll::as_equation_slope(bool exp) const
{
    vector<unique_ptr<Equation>> result;

    vector<Slope> candidates = {
        Slope(_a, _b),
        Slope(_a, _c),
        Slope(_b, _c),
    };

    vector<Slope> valid_slopes;
    for (const auto &s : candidates)
    {
        if (s.check_numerically())
        {
            valid_slopes.push_back(s);
        }
    }

    // 3. 两两配对，生成 p - q = 0 的方程
    for (size_t i = 0; i < valid_slopes.size(); ++i)
    {
        for (size_t j = i + 1; j < valid_slopes.size(); ++j)
        {
            vector<Term> terms = {
                Term(valid_slopes[i]),
                -Term(valid_slopes[j])};

            result.push_back(make_unique<Equation>(Equation(std::move(terms))));
        }
    }

    return result;
}

vector<unique_ptr<Equation>> Coll::as_equation_dist(bool exp) const
{
    vector<unique_ptr<Equation>> result;
    vector<Term> candidates = {
        Term(Dist(_a, _b)),
        Term(Dist(_a, _c)),
        Term(Dist(_b, _c)),
    };
    sort(candidates.begin(), candidates.end(), [](const Term &a, const Term &b)
         { return a.to_double() < b.to_double(); });
    result.push_back(make_unique<Equation>(Equation({candidates[0], candidates[1], -candidates[2]})));
    return result;
}

Coll Coll::reverse() const
{
    return {_c, _b, _a};
}

unique_ptr<Statement> Coll::replace(Point p, Point q) const
{
    Point new_a = (_a == p) ? q : _a;
    Point new_b = (_b == p) ? q : _b;
    Point new_c = (_c == p) ? q : _c;
    return std::make_unique<Coll>(new_a, new_b, new_c);
}