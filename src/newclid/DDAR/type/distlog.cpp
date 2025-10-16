#include "type/distlog.hpp"
#include <cmath>

using namespace std;

double DistLog::to_double() const
{
    return log(_value.to_double());
}

vector<Point> DistLog::points() const
{
    return _value.points();
}

bool DistLog::check_nondegen() const
{
    return _value.check_nondegen();
}

ostream &operator<<(ostream &os, const DistLog &dist)
{
    os << "log(" << dist.value() << ")";
    return os;
}

DistLog DistLog::normalize() const
{
    return DistLog(_value.normalize());
}