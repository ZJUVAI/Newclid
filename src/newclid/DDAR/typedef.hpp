#ifndef TYPEDEF_HPP
#define TYPEDEF_HPP

#include "type/point.hpp"
#include "type/triangle.hpp"
#include "type/rational.hpp"
#include "type/dist.hpp"
#include "type/angle.hpp"
#include "type/slope.hpp"
#include "type/distlog.hpp"
#include "type/pi.hpp"
#include <sstream>

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

struct term_arg
{
    enum class Type
    {
        SlopeType,
        DistType,
        DistLogType,
        PiType,
    } type;

    union
    {
        Dist dist;
        Slope slope;
        DistLog distlog;
        Pi pi;
    };

    term_arg(const Dist &d) : type(Type::DistType), dist(d) {}
    term_arg(const Slope &s) : type(Type::SlopeType), slope(s) {}
    term_arg(const DistLog &dlog) : type(Type::DistLogType), distlog(dlog) {}

    term_arg(const Pi &p) : type(Type::PiType), pi(p) {}

    term_arg(const term_arg &other) : type(other.type)
    {
        switch (type)
        {
        case Type::DistType:
            new (&dist) Dist(other.dist);
            break;
        case Type::SlopeType:
            new (&slope) Slope(other.slope);
            break;
        case Type::DistLogType:
            new (&distlog) DistLog(other.distlog);
            break;
        case Type::PiType:
            new (&pi) Pi(other.pi);
            break;
        }
    }

    ~term_arg()
    {
        if (type == Type::DistType)
            dist.~Dist();
        else if (type == Type::SlopeType)
            slope.~Slope();
        else if (type == Type::DistLogType)
            distlog.~DistLog();
        else if (type == Type::PiType)
            pi.~Pi();
    }

    double to_double() const
    {
        if (type == Type::DistType)
            return dist.to_double();
        else if (type == Type::SlopeType)
            return slope.angle();
        else if (type == Type::DistLogType)
            return distlog.to_double();
        else if (type == Type::PiType)
            return pi.to_double();
        return 0;
    }

    std::string to_string() const
    {
        std::ostringstream oss;

        if (type == Type::DistType)
        {
            oss << dist;
        }
        else if (type == Type::SlopeType)
        {
            oss << slope;
        }
        else if (type == Type::DistLogType)
        {
            oss << distlog;
        }
        else if (type == Type::PiType)
        {
            oss << pi;
        }

        return oss.str(); // 返回字符串
    }

    bool operator<(const term_arg &other) const
    {
        return this->to_string() < other.to_string();
    }
};

inline bool operator==(const term_arg &a, const term_arg &b) noexcept
{
    return a.to_string() == b.to_string();
}

namespace std
{
    template <>
    struct hash<term_arg>
    {
        size_t operator()(const term_arg &t) const noexcept
        {
            return std::hash<std::string>{}(t.to_string());
        }
    };
}

#endif // TYPEDEF_HPP