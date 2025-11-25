#include "type/product.hpp"
#include <vector>

using namespace std;

double Product::to_double() const
{
    if (_dists.empty())
        return 1.0;
    return accumulate(_dists.begin(), _dists.end(), 1.0,
                    [](double acc, const Dist &d) { return acc * d.to_double(); });
}

bool Product::check_nondegen() const
{
    return accumulate(_dists.begin(), _dists.end(), true,
                    [](bool acc, const Dist &d) { return acc && d.check_nondegen(); });
}

bool Product::operator<(const Product &other) const
{
    size_t n = _dists.size();
    size_t m = other._dists.size();
    size_t len = std::min(n, m);

    for (size_t i = 0; i < len; ++i)
    {
        if (_dists[i] < other._dists[i])
            return true;
        else if (_dists[i] > other._dists[i])
            return false;
    }
    return n < m;
}

bool Product::operator==(const Product &other) const
{
    if (_dists.size() != other._dists.size())
        return false;

    for (size_t i = 0; i < _dists.size(); ++i)
    {
        if (!(_dists[i] == other._dists[i]))
            return false;
    }
    return true;
}

bool Product::operator>(const Product &other) const
{
    return other < *this;
}

bool Product::operator!=(const Product &other) const
{
    return !(*this == other);
}

bool Product::operator>=(const Product &other) const
{
    return !(*this < other);
}

bool Product::operator<=(const Product &other) const
{
    return !(*this > other);
}

Product Product::normalize() const
{
    vector<Dist> sorted_dists = _dists;
    sort(sorted_dists.begin(), sorted_dists.end());
    return Product(sorted_dists);
}

ostream &operator<<(ostream &os, const Product &p)
{
    os << "Product(";
    auto dists = p.dists();
    for (size_t i = 0; i < dists.size(); i++)
    {
        os << dists[i];
        if (i != dists.size() - 1)
            os << ", ";
    }
    os << ")";
    return os;
}
