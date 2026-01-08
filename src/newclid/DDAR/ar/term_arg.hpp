#ifndef TERM_ARG_HPP
#define TERM_ARG_HPP

#include <vector>
#include <string>
#include <algorithm>
#include "type/point.hpp"

class Slope;
class Dist;
class DistLog;

class TermArg
{
public:
    enum class ArgType
    {
        Dist,
        DistLog,
        Slope,
        Pi
    };

private:
    ArgType _type;
    std::vector<Point> _points;

    void sort_points();

public:
    TermArg() = default;

    explicit TermArg(std::string t, std::vector<Point> pts = {});

    TermArg(ArgType t, std::vector<Point> pts = {});

    TermArg(Slope s);
    TermArg(Dist d);
    TermArg(DistLog d);

    ArgType type() const { return _type; }
    const std::vector<Point> &points() const { return _points; }

    std::string to_string() const;
    double to_double() const;

    bool operator==(const TermArg &other) const;
    bool operator!=(const TermArg &other) const;
    bool operator<(const TermArg &other) const;
};

namespace std
{
    template <>
    struct hash<TermArg>
    {
        size_t operator()(const TermArg &t) const noexcept
        {
            return std::hash<std::string>{}(t.to_string());
        }
    };
}

#endif // TERM_ARG_HPP