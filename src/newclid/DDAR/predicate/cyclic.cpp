#include "predicate/cyclic.hpp"
#include "predicate/coll.hpp"
#include "type/angle.hpp"
#include <iostream>

using namespace std;

Cyclic::Cyclic(Point a, Point b, Point c, Point d) : _a(a), _b(b), _c(c), _d(d)
{
}

Cyclic::Cyclic(const vector<statement_arg> &args) : _a(args[0].point), _b(args[1].point), _c(args[2].point), _d(args[3].point)
{
}

string Cyclic::name() const
{
    return "cyclic";
}

vector<Point> Cyclic::points() const
{
    return {_a, _b, _c, _d};
}

unique_ptr<Statement> Cyclic::clone() const
{
    return make_unique<Cyclic>(*this);
}

unique_ptr<Statement> Cyclic::normalize() const
{
    vector<Point> pts = points();
    sort(pts.begin(), pts.end());
    return make_unique<Cyclic>(pts[0], pts[1], pts[2], pts[3]);
}

bool Cyclic::check_nondegen() const
{
    return eqangles_cad_cbd().check_nondegen() && eqangles_bad_bcd().check_nondegen() && !Coll(_a, _b, _c).check_equations();
}

bool Cyclic::check_equations() const
{
    return eqangles_abd_acd().check_equations();
}

vector<statement_arg> Cyclic::args() const
{
    return {_a, _b, _c, _d};
}

EqAngle Cyclic::eqangles_cad_cbd() const
{
    return EqAngle(Angle(_c, _a, _d), Angle(_c, _b, _d));
}

EqAngle Cyclic::eqangles_bad_bcd() const
{
    return EqAngle(Angle(_b, _a, _d), Angle(_b, _c, _d));
}

EqAngle Cyclic::eqangles_abd_acd() const
{
    return EqAngle(Angle(_a, _b, _d), Angle(_a, _c, _d));
}

ostream &Cyclic::print(ostream &os) const
{
    return os << _a << " ∈ ω(" << _b << _c << _d << ")";
}

vector<Cyclic> Cyclic::permutation() const
{
    vector<Cyclic> res;
    res.reserve(3);
    res.push_back(Cyclic(_a, _b, _c, _d));
    res.push_back(Cyclic(_a, _c, _b, _d));
    res.push_back(Cyclic(_b, _c, _a, _d));
    return res;
}