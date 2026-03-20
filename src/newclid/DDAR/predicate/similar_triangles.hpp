#ifndef SIMILAR_TRIANGLES_HPP
#define SIMILAR_TRIANGLES_HPP

#include "predicate/statement.hpp"
#include "type/triangle.hpp"
#include "type/point.hpp"
#include "predicate/eqratio.hpp"
#include "predicate/eqangle.hpp"
#include "predicate/sameclock.hpp"

class SimilarTriangles : public Statement
{
private:
    Triangle _left;
    Triangle _right;
    bool _sameclock;

public:
    SimilarTriangles(const Triangle &t1, const Triangle &t2, bool sameclock);

    SimilarTriangles(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> clone() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const;

    const Triangle &left() const { return _left; }

    const Triangle &right() const { return _right; }

    bool sameclock() const { return _sameclock; }

    SameClock to_sameclock() const;

    EqRatio eqratio_abbc() const;

    EqRatio eqratio_abac() const;

    EqRatio eqratio_bcac() const;

    EqAngle eqangle_abc() const;

    EqAngle eqangle_bca() const;

    EqAngle eqangle_acb() const;

    EqAngle eqangle_cab() const;

    std::vector<SimilarTriangles> permutations() const;

    std::vector<SimilarTriangles> cyclic_rotations() const;

    std::ostream &print(std::ostream &os) const override;

    bool numerical_only() const { return false; }

    bool operator==(const SimilarTriangles &other) const;

    bool operator!=(const SimilarTriangles &other) const;

    bool operator<(const SimilarTriangles &other) const;

    bool operator>(const SimilarTriangles &other) const;

    bool operator<=(const SimilarTriangles &other) const;

    bool operator>=(const SimilarTriangles &other) const;
};

#endif // SIMILAR_TRIANGLES_HPP