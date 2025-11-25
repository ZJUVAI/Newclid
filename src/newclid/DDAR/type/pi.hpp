#ifndef PI_HPP
#define PI_HPP

#include <cmath>
#include <string>
#include <iostream>

class Pi final
{
public:
    Pi() = default;

    double to_double() const { return M_PI; }

    std::string to_string() const { return "π"; }
};

std::ostream &operator<<(std::ostream &os, const Pi &pi);

#endif // PI_HPP