#ifndef DIST_HPP
#define DIST_HPP

#include "type/point.hpp"
#include <vector>

class Dist final
{
private:
    Point _left;
    Point _right;

public:
    Dist(Point p1, Point p2);

    const Point &left() const { return _left; }

    const Point &right() const { return _right; }

    double to_double() const;

    std::vector<Point> points() const { return {_left, _right}; }

    bool check_nondegen() const
    {
        return !_left.is_close(_right);
    }

    bool operator<(const Dist &other) const;

    bool operator==(const Dist &other) const;

    bool operator>(const Dist &other) const;

    Dist normalize() const;
};

std::ostream &operator<<(std::ostream &os, const Dist &dist);

namespace std
{
    template <>
    struct hash<Dist>
    {
        size_t operator()(const Dist &dist) const
        {
            return std::hash<std::string>()(dist.left().name() + dist.right().name());
        }
    };
}

#endif // DIST_HPP