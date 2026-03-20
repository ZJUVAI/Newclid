#ifndef LINEAR_COMBINATION_HPP
#define LINEAR_COMBINATION_HPP

#include <vector>
#include <iostream>
#include "ar/term.hpp"
#include "type/rational.hpp"

class LinearCombination final
{
private:
    std::vector<Term> _terms;

public:
    LinearCombination() : _terms() {}

    LinearCombination(std::vector<Term> terms);

    LinearCombination(Term &term) : _terms({term}) {}

    LinearCombination &operator+=(const LinearCombination &other);
    LinearCombination operator+(const LinearCombination &other) const;

    LinearCombination &operator-=(const LinearCombination &other);
    LinearCombination operator-(const LinearCombination &other) const;

    LinearCombination &operator*=(const Rational &multiplier);
    LinearCombination operator*(const Rational &multiplier) const;

    LinearCombination &operator*=(const Term &multiplier);
    LinearCombination operator*(const Term &multiplier) const;

    LinearCombination operator-() const;

    void normalize();

    Term gcd();

    std::vector<Term>::const_iterator begin() const;
    std::vector<Term>::const_iterator end() const;

    const std::vector<Term> &terms() const { return _terms; }

    bool empty() const { return _terms.empty(); }

    bool operator<(const LinearCombination &other) const { return _terms < other._terms; }

    bool operator==(const LinearCombination &other) const
    {
        if (_terms.size() != other._terms.size())
        {
            return false;
        }
        for (size_t i = 0; i < _terms.size(); ++i)
        {
            const Term &a = _terms[i];
            const Term &b = other._terms[i];
            if (a != b || a.coeff() != b.coeff())
            {
                return false;
            }
        }
        return true;
    }

    size_t size() const { return _terms.size(); }
};

std::ostream &operator<<(std::ostream &os, const LinearCombination &lc);

namespace std
{
    template <>
    struct hash<LinearCombination>
    {
        size_t operator()(const LinearCombination &lc) const noexcept
        {
            size_t seed = 0;

            for (const auto &t : lc.terms())
            {
                seed ^= hash<string>()(t.to_string()) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
            }

            return seed;
        }
    };
}

#endif // LINEAR_COMBINATION_HPP