#ifndef RATLOG_HPP
#define RATLOG_HPP

#include "type/rational.hpp"

// Not Used
class RationalLog
{
private:
    Rational _value;

public:
    RationalLog(Rational value);

    RationalLog() : _value(Rational(1)) {}

    Rational value() const { return _value; }

    RationalLog operator+(const RationalLog &other) const;
    RationalLog operator-(const RationalLog &other) const;

    RationalLog &operator+=(const RationalLog &other);
    RationalLog &operator-=(const RationalLog &other);

    RationalLog operator-() const;

    bool operator==(const RationalLog &other) const;
    bool operator!=(const RationalLog &other) const;
    bool operator<(const RationalLog &other) const;
    bool operator<=(const RationalLog &other) const;
    bool operator>(const RationalLog &other) const;
    bool operator>=(const RationalLog &other) const;
};

std::ostream &operator<<(std::ostream &os, const RationalLog &ratlog);

#endif // RATLOG_HPP