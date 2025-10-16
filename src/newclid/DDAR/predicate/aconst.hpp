#ifndef ACONST_HPP
#define ACONST_HPP

#include <memory>
#include <string>
#include <vector>
#include "predicate/statement.hpp"
#include "type/rational.hpp"

class AConst : public Statement
{
public:
    AConst(const Angle &ang, const Rational &rhs);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    const Angle &angle() const { return _angle; }

    const Rational &rhs() const { return _rhs; }

    std::unique_ptr<Statement> clone() const override
    {
        return std::make_unique<AConst>(*this);
    }

    Equation<Slope> *as_equation_slope() const override;

    std::ostream &print(std::ostream &out) const override;

    bool numerical_only() const { return false; }

    ~AConst() override = default;

private:
    Angle _angle;
    Rational _rhs;
};

#endif // ACONST_HPP