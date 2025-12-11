#ifndef NPARA_HPP
#define NPARA_HPP

#include "predicate/statement.hpp"

class NPara : public Statement
{
public:
    NPara(const Slope &left, const Slope &right);

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

    bool numerical_only() const { return true; }

    bool trivial() const { return false; }

private:
    Slope _left;
    Slope _right;
};

#endif // NPARA_HPP