#ifndef TRIANGLE_HPP
#define TRIANGLE_HPP

#include "type/point.hpp"
#include "type/angle.hpp"
#include "type/dist.hpp"
#include <vector>

class Triangle final
{
private:
    Point _a, _b, _c;

public:
    Triangle() = delete;

    Triangle(Point a, Point b, Point c);

    double area() const;

    const Point &a() const { return _a; }

    const Point &b() const { return _b; }

    const Point &c() const { return _c; }

    std::vector<Point> points() const { return {_a, _b, _c}; }

    Angle angle_a() const;

    Angle angle_b() const;

    Angle angle_c() const;

    Dist dist_ab() const;

    Dist dist_bc() const;

    Dist dist_ac() const;

    Point operator[](size_t ind) const;

    std::vector<Triangle> cyclic_rotations() const;

    std::vector<Triangle> permutations() const;

    std::vector<Dist> dists() const;

    std::vector<Angle> angles() const;

    bool check_nondegen() const;

    Triangle normalize() const;

    bool operator==(const Triangle &other) const;

    bool operator<(const Triangle &other) const;
};

std::ostream &operator<<(std::ostream &os, const Triangle &triangle);

#endif // TRIANGLE_HPP