#ifndef PAPPUS_HPP
#define PAPPUS_HPP

#include "predicate/statement.hpp"
#include "predicate/coll.hpp"

class Pappus : public Statement
{
private:
    Coll _left;
    Coll _middle;
    Coll _right;

public:
    Pappus(const Coll &left, const Coll &middle, const Coll &right);

    Pappus(const std::vector<statement_arg> &args);

    const Coll &left() const { return _left; }

    const Coll &middle() const { return _middle; }

    const Coll &right() const { return _right; }

    std::string name() const override;

    std::vector<Point> points() const override;

    std::unique_ptr<Statement> replace(Point p, Point q) const override;

    std::unique_ptr<Statement> normalize() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    std::ostream &print(std::ostream &os) const override;

    std::vector<Pappus> permutations() const;

    bool numerical_only() const { return false; }

    bool trivial() const { return false; }

    bool operator==(const Pappus &other) const;

    bool operator!=(const Pappus &other) const;

    bool operator<(const Pappus &other) const;

    bool operator>(const Pappus &other) const;

    bool operator<=(const Pappus &other) const;

    bool operator>=(const Pappus &other) const;

    Coll coll_ab() const;

    Coll coll_ba() const;

    Coll coll_bc() const;

    Coll coll_cb() const;

    Coll coll_ac() const;

    Coll coll_ca() const;
};

#endif // PAPPUS_HPP