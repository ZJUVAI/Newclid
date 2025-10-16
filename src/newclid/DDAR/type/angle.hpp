#ifndef ANGLE_HPP
#define ANGLE_HPP

#include "type/point.hpp"
#include "type/slope.hpp"

class Angle final
{
private:
    Point _left_pt;
    Point _vertex_pt;
    Point _right_pt;

public:
    Angle(Point left_pt, Point vertex_pt, Point right_pt);

    Angle(Point p1, Point p2, Point p3, Point p4);

    Angle() = delete;

    const Point &left() const { return _left_pt; }

    const Point &right() const { return _right_pt; }

    const Point &vertex() const { return _vertex_pt; }

    Slope left_side() const;

    Slope right_side() const;

    Angle operator-() const
    {
        return {_right_pt, _vertex_pt, _left_pt};
    }

    double dot_product() const;

    std::vector<Point> points() const { return {_left_pt, _vertex_pt, _right_pt}; }

    double angle() const;

    bool check_nondegen() const;

    bool operator==(const Angle &other) const;

    bool operator!=(const Angle &other) const;

    bool operator<(const Angle &other) const;

    bool operator<=(const Angle &other) const;

    bool operator>(const Angle &other) const;

    bool operator>=(const Angle &other) const;
};

std::ostream &operator<<(std::ostream &os, const Angle &angle);

#endif // ANGLE_HPP