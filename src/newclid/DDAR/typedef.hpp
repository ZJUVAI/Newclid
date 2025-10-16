#ifndef TYPEDEF_HPP
#define TYPEDEF_HPP

#include "type/point.hpp"
#include "type/triangle.hpp"
#include "type/rational.hpp"
#include "type/dist.hpp"
#include "type/angle.hpp"
#include "type/slope.hpp"

struct statement_arg
{
    enum class Type
    {
        PointType,
        BoolType,
        TriangleType,
        RationalType,
        DistType,
        AngleType,
        SlopeType
    } type;

    union
    {
        Point point;
        bool b;
        Triangle tri;
        Rational rat;
        Dist dist;
        Angle angle;
        Slope slope;
    };

    statement_arg(const Point &p) : type(Type::PointType), point(p) {}
    statement_arg(bool val) : type(Type::BoolType), b(val) {}
    statement_arg(const Triangle &t) : type(Type::TriangleType), tri(t) {}
    statement_arg(const Rational &r) : type(Type::RationalType), rat(r) {}
    statement_arg(const Dist &d) : type(Type::DistType), dist(d) {}
    statement_arg(const Slope &s) : type(Type::SlopeType), slope(s) {}
    statement_arg(const Angle &a) : type(Type::AngleType), angle(a) {}

    statement_arg(const statement_arg &other) : type(other.type)
    {
        switch (type)
        {
        case Type::PointType:
            new (&point) Point(other.point);
            break;
        case Type::BoolType:
            b = other.b;
            break;
        case Type::TriangleType:
            new (&tri) Triangle(other.tri);
            break;
        case Type::RationalType:
            new (&rat) Rational(other.rat);
            break;
        case Type::DistType:
            new (&dist) Dist(other.dist);
            break;
        case Type::SlopeType:
            new (&slope) Slope(other.slope);
            break;
        case Type::AngleType:
            new (&angle) Angle(other.angle);
            break;
        }
    }

    ~statement_arg()
    {
        if (type == Type::PointType)
            point.~Point();
        else if (type == Type::TriangleType)
            tri.~Triangle();
        else if (type == Type::RationalType)
            rat.~Rational();
        else if (type == Type::DistType)
            dist.~Dist();
        else if (type == Type::AngleType)
            angle.~Angle();
        else if (type == Type::SlopeType)
            slope.~Slope();
    }
};

#endif // TYPEDEF_HPP