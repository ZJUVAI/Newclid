#include "type/pi.hpp"

using namespace std;

ostream &operator<<(ostream &os, const Pi &pi)
{
    os << pi.to_string();
    return os;
}