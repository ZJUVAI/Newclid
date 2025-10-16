#ifndef POINTNUM_HPP
#define POINTNUM_HPP
#include <string>
#include <cmath>
#include "numerical.hpp"

class PointNum final
{
private:
    double _x;
    double _y;

public:
    PointNum(double x, double y);

    double x() const;

    double y() const;

    PointNum operator+(const PointNum &other) const;

    PointNum operator-(const PointNum &other) const;

    PointNum operator*(double scalar) const;

    double operator*(const PointNum &other) const;

    PointNum operator/(double scalar) const;

    std::string to_string() const;

    double abs() const;

    double angle() const;

    bool close_enough(const PointNum &other) const;

    double distance(const PointNum &other) const;

    double distance2(const PointNum &other) const;

    void rotate(double angle);
};

#endif // POINTNUM_HPP