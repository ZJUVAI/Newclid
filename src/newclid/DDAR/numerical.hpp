#ifndef NUMERICAL_HPP
#define NUMERICAL_HPP
#include <cmath>
#include <algorithm>

class Numerical
{
public:
    static bool close_enough(const double &a, const double &b);

    static bool nearly_zero(double x);

    static int sign(double x);

private:
    static constexpr double ATOM = 1e-9;
    static constexpr double REL_TOL = 0.001;
};

#endif // NUMERICAL_HPP