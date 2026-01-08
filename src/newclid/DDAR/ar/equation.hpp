#ifndef EQUATION_HPP
#define EQUATION_HPP

#include <vector>
#include <iostream>
#include "ar/term.hpp"
#include "ar/equation_index.hpp"
#include "type/rational.hpp"

class LinearSystem;
class ObjectTable;

class Equation final
{
private:
    std::vector<Term> _terms;
    std::vector<std::pair<double, EquationIndex>> _combination;
    ObjectTable *_table;

public:
    Equation(ObjectTable *table = nullptr) : _terms(), _combination({std::make_pair(1.0, EquationIndex(-1, nullptr))}), _table(std::move(table)) {}

    Equation(std::vector<Term> terms, ObjectTable *table = nullptr);

    Equation(Term &term, ObjectTable *table = nullptr) : _terms({term}), _combination({std::make_pair(1.0, EquationIndex(-1, nullptr))}), _table(std::move(table)) {}

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

    bool operator==(const Equation &other) const
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

std::ostream &operator<<(std::ostream &os, const Equation &eq);

namespace std
{
    template <>
    struct hash<Equation>
    {
        size_t operator()(const Equation &eq) const noexcept
        {
            size_t seed = 0;

            for (const auto &t : eq.terms())
            {
                seed ^= hash<string>()(t.to_string()) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
            }

            return seed;
        }
    };
}

#endif // EQUATION_HPP