#include "predicate/congruent_triangles.hpp"
#include "predicate/statement.hpp"
#include "type/triangle.hpp"
#include "predicate/similar_triangles.hpp"
#include "predicate/cong.hpp"
#include <vector>
#include <iostream>

using namespace std;

CongruentTriangles::CongruentTriangles(const Triangle &t1, const Triangle &t2, bool sameclock)
    : SimilarTriangles(t1, t2, sameclock)
{
}

CongruentTriangles::CongruentTriangles(const vector<statement_arg> &args)
    : SimilarTriangles(args)
{
}

string CongruentTriangles::name() const
{
    return sameclock() ? "contri" : "contrir";
}

unique_ptr<Statement> CongruentTriangles::clone() const
{
    return make_unique<CongruentTriangles>(*this);
}

bool CongruentTriangles::check_equations() const
{
    return cong_ab().check_equations() && cong_bc().check_equations() && cong_ac().check_equations();
}

unique_ptr<Statement> CongruentTriangles::normalize() const
{
    auto base = dynamic_cast<const SimilarTriangles &>(*SimilarTriangles::normalize());
    return make_unique<CongruentTriangles>(base.left(), base.right(), base.sameclock());
}

Cong CongruentTriangles::cong_ab() const
{
    return {left().dist_ab(), right().dist_ab()};
}

Cong CongruentTriangles::cong_bc() const
{
    return {left().dist_bc(), right().dist_bc()};
}

Cong CongruentTriangles::cong_ac() const
{
    return {left().dist_ac(), right().dist_ac()};
}

ostream &CongruentTriangles::print(ostream &os) const
{
    return os << left() << (sameclock() ? " ≅ " : " ≅r ") << right();
}

vector<CongruentTriangles> CongruentTriangles::cyclic_rotations() const
{
    const auto l = left().cyclic_rotations();
    const auto r = right().cyclic_rotations();
    return {CongruentTriangles(l[0], r[0], sameclock()),
            CongruentTriangles(l[1], r[1], sameclock()),
            CongruentTriangles(l[2], r[2], sameclock())};
}