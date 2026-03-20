#ifndef THALES_HPP
#define THALES_HPP

#include "predicate/statement.hpp"
#include "predicate/coll.hpp"
#include "predicate/para.hpp"

class Thales : public Statement
{
private:
    Coll _left;
    Coll _right;

public:
    Thales(Coll left, Coll right);

    Thales(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    std::ostream &print(std::ostream &os) const override;

    std::vector<Thales> permutations() const;

    Para para_ab() const;

    Para para_bc() const;

    Para para_ac() const;

    Coll left() const { return _left; }

    Coll right() const { return _right; }

    Thales rotate() const;

    bool numerical_only() const { return false; }

    bool operator==(const Thales &other) const;

    bool operator!=(const Thales &other) const;

    bool operator<(const Thales &other) const;

    bool operator>(const Thales &other) const;

    bool operator<=(const Thales &other) const;

    bool operator>=(const Thales &other) const;
};

#endif // THALES_HPP