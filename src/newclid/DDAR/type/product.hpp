#ifndef PRODUCT_HPP
#define PRODUCT_HPP

#include "type/dist.hpp"
#include <vector>
#include <numeric>
#include <ostream>

class Product final
{
private:
    std::vector<Dist> _dists;

public:
    Product() = default;
    Product(const std::vector<Dist> &dists) : _dists(dists) {}

    Product(const Dist &dist) : _dists({dist}) {}

    void add(const Dist &dist) { _dists.push_back(dist); }

    const std::vector<Dist> &dists() const { return _dists; }

    double to_double() const;

    bool check_nondegen() const;

    bool operator<(const Product &other) const;
    bool operator==(const Product &other) const;
    bool operator!=(const Product &other) const;
    bool operator>(const Product &other) const;
    bool operator>=(const Product &other) const;
    bool operator<=(const Product &other) const;

    Product normalize() const;
};

std::ostream &operator<<(std::ostream &os, const Product &product);

namespace std
{
    template <>
    struct hash<Product>
    {
        size_t operator()(const Product &pro) const
        {
            std::string s;
            for (auto &d : pro.dists())
            {
                s = s + d.left().name() + d.right().name();
            }
            return std::hash<std::string>{}(s);
        }
    };
}

#endif // PRODUCT_HPP
