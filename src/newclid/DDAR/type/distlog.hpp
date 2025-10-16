#ifndef DISTLOG_HPP
#define DISTLOG_HPP

#include "type/dist.hpp"

class DistLog
{
private:
    Dist _value;

public:
    DistLog(Dist value) : _value(value) {}

    Dist value() const { return _value; }

    double to_double() const;

    std::vector<Point> points() const;

    bool check_nondegen() const;

    bool operator==(const DistLog &other) const { return _value == other._value; }

    bool operator<(const DistLog &other) const { return _value < other._value; }

    bool operator>(const DistLog &other) const { return _value > other._value; }

    DistLog normalize() const;
};

std::ostream &operator<<(std::ostream &os, const DistLog &dist);

namespace std
{
    template <>
    struct hash<DistLog>
    {
        size_t operator()(const DistLog &log) const
        {
            return std::hash<Dist>()(log.value());
        }
    };
}

#endif // DISTLOG_HPP