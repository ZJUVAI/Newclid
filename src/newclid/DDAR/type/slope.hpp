#ifndef SLOPE_HPP
#define SLOPE_HPP

#include "type/point.hpp"
#include <vector>

#define M_PI 3.14159265358979323846

class Slope final
{
private:
    Point _left;
    Point _right;

public:
    Slope(Point p1, Point p2);

    bool check_numerically();

    bool check_nondegen() const { return !_left.is_close(_right); }

    const Point &left() const { return _left; }

    const Point &right() const { return _right; }

    std::vector<Point> points() const { return {_left, _right}; }

    bool operator<(const Slope &other) const;

    bool operator==(const Slope &other) const;

    bool operator>(const Slope &other) const;

    double angle() const;

    Slope normalize() const;
};

std::ostream &operator<<(std::ostream &os, const Slope &slope_angle);

namespace std
{
    template <>
    struct hash<Slope>
    {
        size_t operator()(const Slope &slope) const
        {
            return std::hash<std::string>()(slope.left().name() + slope.right().name());
        }
    };
}

#endif // SLOPE_HPP