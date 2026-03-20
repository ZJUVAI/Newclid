#ifndef CIRCUMCENTER_HPP
#define CIRCUMCENTER_HPP

#include "type/triangle.hpp"
#include "predicate/cong.hpp"
#include "predicate/statement.hpp"

class CircumCenter : public Statement
{
public:
    CircumCenter(Point center, Triangle triangle);

    CircumCenter(const std::vector<statement_arg> &args);

    std::string name() const override;

    std::vector<Point> points() const override;

    bool check_nondegen() const override;

    bool check_equations() const override;

    std::vector<statement_arg> args() const override;

    std::unique_ptr<Statement> clone() const override;

    Cong cong_ab() const;

    Cong cong_bc() const;

    Cong cong_ac() const;

    const Point &center() const { return _center; }

    const Triangle &triangle() const { return _triangle; }

    const Point &a() const { return _triangle.a(); }

    const Point &b() const { return _triangle.b(); }

    const Point &c() const { return _triangle.c(); }

    std::ostream &print(std::ostream &os) const override;

    bool numerical_only() const { return false; }

    std::unique_ptr<Statement> normalize() const override;

private:
    Point _center;
    Triangle _triangle;
};

#endif // CIRCUMCENTER_HPP