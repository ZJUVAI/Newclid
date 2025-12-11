#ifndef SAMESIDE_HPP
#define SAMESIDE_HPP

#include "predicate/statement.hpp"
#include "predicate/coll.hpp"

class SameSide : public Statement
{
private:
    Point _a;
    Point _b;
    Point _c;
    Point _d;
    Point _e;
    Point _f;

public:
    SameSide(const Point &a, const Point &b, const Point &c, const Point &d, const Point &e, const Point &f);

    SameSide(const Coll &left, const Coll &right);

    SameSide(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    const Point &a() const { return _a; }

    const Point &b() const { return _b; }

    const Point &c() const { return _c; }

    const Point &d() const { return _d; }

    const Point &e() const { return _e; }

    const Point &f() const { return _f; }

    std::ostream &print(std::ostream &os) const override;

    bool numerical_only() const { return true; }

    bool trivial() const { return false; }
};

#endif // SAMESIDE_HPP