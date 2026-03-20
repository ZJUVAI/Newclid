#ifndef SAMECLOCK_HPP
#define SAMECLOCK_HPP

#include "predicate/statement.hpp"
#include "type/triangle.hpp"

class SameClock : public Statement
{
private:
    Triangle _left;
    Triangle _right;

public:
    SameClock(const Triangle &left, const Triangle &right);

    std::string name() const override;

    std::vector<Point> points() const;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::unique_ptr<Statement> replace(Point p, Point q) const override;

    std::unique_ptr<Statement> normalize() const override;

    const Triangle &left() const { return _left; }

    const Triangle &right() const { return _right; }

    std::ostream &print(std::ostream &out) const override;

    bool numerical_only() const { return true; }

    bool trivial() const { return false; }
};

#endif // SAMECLOCK_HPP