#include "type/ratlog.hpp"
#include "type/rational.hpp"

using namespace std;

RationalLog::RationalLog(Rational value) : _value(value)
{
    if (value < 0)
    {
        throw runtime_error("RationalLog value must be non-negative.");
    }
}

RationalLog RationalLog::operator+(const RationalLog &other) const
{
    return RationalLog(_value * other._value);
}

RationalLog RationalLog::operator-(const RationalLog &other) const
{
    return RationalLog(_value / other._value);
}

RationalLog &RationalLog::operator+=(const RationalLog &other)
{
    *this = *this + other;
    return *this;
}

RationalLog &RationalLog::operator-=(const RationalLog &other)
{
    *this = *this - other;
    return *this;
}

RationalLog RationalLog::operator-() const
{
    return RationalLog(Rational(1) / _value);
}

bool RationalLog::operator==(const RationalLog &other) const
{
    return _value == other._value;
}

bool RationalLog::operator!=(const RationalLog &other) const
{
    return _value != other._value;
}

bool RationalLog::operator<(const RationalLog &other) const
{
    return _value < other._value;
}
bool RationalLog::operator<=(const RationalLog &other) const
{
    return _value <= other._value;
}

bool RationalLog::operator>(const RationalLog &other) const
{
    return _value > other._value;
}

bool RationalLog::operator>=(const RationalLog &other) const
{
    return _value >= other._value;
}

ostream &operator<<(ostream &os, const RationalLog &ratlog)
{
    os << "log(" << ratlog.value() << ")";
    return os;
}