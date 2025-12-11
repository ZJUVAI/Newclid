#ifndef MIDPOINT_HPP
#define MIDPOINT_HPP

#include "predicate/statement.hpp"
#include "predicate/cong.hpp"
#include "predicate/coll.hpp"
#include "type/point.hpp"
#include "type/product.hpp"

class Midp : public Statement
{
private:
    Point _middle;
    Point _left;
    Point _right;

public:
    Midp(Point middle, Point left, Point right);

    Midp(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    std::ostream &print(std::ostream &os) const override;

    Coll to_coll() const;

    Cong to_cong() const;

    const Point &left() const { return _left; }

    const Point &right() const { return _right; }

    const Point &middle() const { return _middle; }

    bool numerical_only() const { return false; }

    bool trivial() const { return _left == _right && _left == _middle; }
};

#endif // MIDPOINT_HPP