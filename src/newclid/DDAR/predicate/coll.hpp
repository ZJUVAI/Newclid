#ifndef COLL_HPP
#define COLL_HPP

#include "predicate/statement.hpp"
#include "predicate/eqratio.hpp"
#include "typedef.hpp"

class Coll : public Statement
{
private:
    Point _a;
    Point _b;
    Point _c;

public:
    Coll(Point a, Point b, Point c);

    Coll(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    std::vector<statement_arg> args() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<Coll> cyclic_rotations() const;

    std::vector<Coll> permutations() const;

    bool is_between() const;

    const Point &a() const { return _a; }

    const Point &b() const { return _b; }

    const Point &c() const { return _c; }

    EqRatio eqratio_ab_bc(const Coll &other) const;

    EqRatio eqratio_ab_ac(const Coll &other) const;

    std::unique_ptr<Statement> clone() const override
    {
        return std::make_unique<Coll>(*this);
    }

    std::ostream &print(std::ostream &os) const override;

    bool numerical_only() const { return false; }

    bool operator==(const Coll &other) const;

    bool operator<(const Coll &other) const;

    Equation<Slope> *as_equation_slope() const override;

    Coll reverse() const;
};

#endif // COLL_HPP