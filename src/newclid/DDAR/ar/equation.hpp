#ifndef EQUATION_HPP
#define EQUATION_HPP

#include <vector>
#include <iostream>
#include "ar/term.hpp"
#include "ar/equation_index.hpp"

class LinearSystem;

class Equation final
{
private:
    std::vector<Term> _terms;
    std::vector<std::pair<double, EquationIndex>> _combination;

public:
    Equation() : _terms(), _combination({std::make_pair(1.0, EquationIndex(-1, nullptr))}) {}

    Equation(std::vector<Term> terms);

    Equation(const Term &term) : _terms({term}), _combination({std::make_pair(1.0, EquationIndex(-1, nullptr))}) {}

    Equation &operator+=(const Equation &other);
    Equation operator+(const Equation &other) const;

    Equation &operator-=(const Equation &other);
    Equation operator-(const Equation &other) const;

    Equation &operator*=(const Rational &multiplier);
    Equation operator*(const Rational &multiplier) const;

    Equation &operator*=(const Term &multiplier);
    Equation operator*(const Term &multiplier) const;

    Equation operator-() const;

    bool empty() const;
    bool linear() const;
    bool check_numerically() const;

    void normalize();
    void reduction();

    std::vector<Term>::const_iterator begin() const;
    std::vector<Term>::const_iterator end() const;

    const std::vector<Term> &terms() const { return _terms; }
    const std::vector<std::pair<double, EquationIndex>> &combination() const { return _combination; }

    void set_index(int n, LinearSystem *system);

    bool operator<(const Equation &other) const { return _terms < other._terms; }

    bool operator==(const Equation &other) const { return _terms == other._terms; }
};

std::ostream &operator<<(std::ostream &os, const Equation &eq);

namespace std
{
    template <>
    struct hash<Equation>
    {
        size_t operator()(const Equation &eq) const noexcept
        {
            size_t seed = 0;
            std::hash<Term> term_hash;

            for (const auto &t : eq.terms())
            {
                seed ^= term_hash(t) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
            }

            return seed;
        }
    };
}

#endif // EQUATION_HPP