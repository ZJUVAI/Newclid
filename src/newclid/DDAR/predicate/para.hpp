#ifndef PARA_HPP
#define PARA_HPP

#include "predicate/statement.hpp"
#include "ar/equation.hpp"

class Para : public Statement
{
private:
    Slope _left;
    Slope _right;

public:
    Para(Slope left, Slope right);

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

    std::vector<Equation<Slope> *> as_equation_slope() const override;

    bool numerical_only() const { return false; }
};

#endif // PARA_HPP