#include "numerical.hpp"
#include "type/slope.hpp"
#include <cmath>
#include <algorithm>

using namespace std;

bool Numerical::close_enough(const double &a, const double &b)
{
    return fabs(a - b) < 4 * ATOM || fabs(a - b) / max(fabs(a), fabs(b)) < REL_TOL;
}

bool Numerical::nearly_zero(double a)
{
    return fabs(a) < 2 * ATOM;
}

int Numerical::sign(double a)
{
    if (Numerical::nearly_zero(a))
        return 0;
    else if (a > 0)
        return 1;
    else
        return -1;
}