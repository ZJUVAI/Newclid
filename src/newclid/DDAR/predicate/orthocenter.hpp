#ifndef ORTHOCENTER_HPP
#define ORTHOCENTER_HPP

#include "predicate/statement.hpp"
#include "type/point.hpp"
#include "type/triangle.hpp"
#include "predicate/perp.hpp"

class OrthoCenter : public Statement
{
private:
    Point _center;
    Triangle _triangle;

public:
    OrthoCenter(const Point &center, const Triangle &triangle);

    OrthoCenter(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> clone() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> normalize() const override;

    std::ostream &print(std::ostream &os) const override;

    Perp perp_a() const;

    Perp perp_b() const;

    Perp perp_c() const;

    const Triangle &triangle() const { return _triangle; }

    const Point &center() const { return _center; }

    const Point &a() const { return _triangle.a(); }

    const Point &b() const { return _triangle.b(); }

    const Point &c() const { return _triangle.c(); }

    std::vector<OrthoCenter> cyclic_rotations() const;

    bool numerical_only() const { return false; }

    bool trivial() const { return false; }
};

#endif // ORTHOCENTER_HPP