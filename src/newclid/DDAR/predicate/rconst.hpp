#ifndef RCONST_HPP
#define RCONST_HPP

#include "predicate/statement.hpp"
#include "ar/equation.hpp"
#include "type/dist.hpp"
#include "type/rational.hpp"
#include <optional>

class RConst : public Statement
{
public:
    RConst(const Dist &left, const Dist &right, const Rational &ratio);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> clone() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    const Dist &left() const { return _left; }

    const Dist &right() const { return _right; }

    const Rational &ratio() const { return _ratio; }

    RConst swap() const;

    std::ostream &print(std::ostream &os) const override;

    Equation<Dist> *as_equation_dist() const override;

    Equation<DistLog> *as_equation_distlog() const override;

    bool numerical_only() const { return false; }

    std::string to_string() const override;

    std::vector<std::string> to_tokens() const;

private:
    Dist _left;
    Dist _right;
    Rational _ratio;
};

#endif // RCONST_HPP