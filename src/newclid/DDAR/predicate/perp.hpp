#ifndef PERP_HPP
#define PERP_HPP

#include "predicate/statement.hpp"
#include "type/slope.hpp"
#include "ar/equation.hpp"
#include "typedef.hpp"

class Perp : public Statement
{
private:
    Slope _left;
    Slope _right;

public:
    Perp(Slope left, Slope right);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    const Slope &left() const { return _left; }

    const Slope &right() const { return _right; }

    std::unique_ptr<Statement> clone() const override;

    std::ostream &print(std::ostream &os) const override;

    Equation<Slope> *as_equation_slope() const override;

    bool numerical_only() const { return false; }
};

#endif // PERP_HPP