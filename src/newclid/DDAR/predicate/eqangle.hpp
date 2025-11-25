#ifndef EQANGLE_HPP
#define EQANGLE_HPP

#include "predicate/statement.hpp"
#include "type/angle.hpp"
#include "type/slope.hpp"
#include "ar/equation.hpp"

class EqAngle : public Statement
{
private:
    Angle _left;
    Angle _right;

public:
    EqAngle(Angle left, Angle right);

    EqAngle(Point p1, Point p2, Point p3, Point p4, Point p5, Point p6, Point p7, Point p8);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> clone() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> normalize() const override;

    std::ostream &print(std::ostream &os) const override;

    std::vector<EqAngle> permutations() const;

    const Angle &left() const { return _left; }

    const Angle &right() const { return _right; }

    std::vector<std::unique_ptr<Equation>> as_equation() const override;

    bool numerical_only() const { return false; }

    bool operator<(const EqAngle &other) const;

    bool operator==(const EqAngle &other) const;

    bool operator!=(const EqAngle &other) const;

    bool operator<=(const EqAngle &other) const;

    bool operator>(const EqAngle &other) const;

    bool operator>=(const EqAngle &other) const;

    std::string to_string() const override;

    std::vector<std::string> to_tokens() const;
};

#endif // EQANGLE_HPP