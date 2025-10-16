#ifndef CYCLIC_HPP
#define CYCLIC_HPP

#include "predicate/statement.hpp"
#include "predicate/eqangle.hpp"
#include "type/point.hpp"

class Cyclic : public Statement
{
private:
    Point _a;
    Point _b;
    Point _c;
    Point _d;

public:
    Cyclic(Point a, Point b, Point c, Point d);

    Cyclic(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const;

    std::unique_ptr<Statement> clone() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const;

    const Point &a() const { return _a; }

    const Point &b() const { return _b; }

    const Point &c() const { return _c; }

    const Point &d() const { return _d; }

    EqAngle eqangles_cad_cbd() const;

    EqAngle eqangles_bad_bcd() const;

    EqAngle eqangles_abd_acd() const;

    std::vector<Cyclic> permutation() const;

    std::ostream &print(std::ostream &os) const override;

    bool numerical_only() const { return false; }
};

#endif // CYCLIC_HPP