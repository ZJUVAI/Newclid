#ifndef EQUATION_HPP
#define EQUATION_HPP

#include <vector>
#include <iostream>
#include "ar/term.hpp"
#include "ar/equation_index.hpp"
#include "ar/linear_combination.hpp"
#include "type/rational.hpp"

class LinearSystem;
class ObjectTable;

class Equation final
{
private:
    LinearCombination _terms;
    std::vector<std::pair<LinearCombination, EquationIndex>> _combination;

public:
    Equation() : _terms(), _combination({std::make_pair(LinearCombination({Term(1)}), EquationIndex(-1, nullptr))}) {}

    Equation(std::vector<Term> terms) : _terms(terms), _combination({std::make_pair(LinearCombination({Term(1)}), EquationIndex(-1, nullptr))}) {}

    Equation(Term &term) : _terms({term}), _combination({std::make_pair(LinearCombination({Term(1)}), EquationIndex(-1, nullptr))}) {}

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

    const LinearCombination &terms() const { return _terms; }
    const std::vector<std::pair<LinearCombination, EquationIndex>> &combination() const { return _combination; }

    void set_index(int n, LinearSystem *system);

    bool operator<(const Equation &other) const { return _terms < other._terms; }

    bool operator==(const Equation &other) const { return _terms == other._terms; }

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
            return std::hash<LinearCombination>()(eq.terms());
        }
    };
}

#endif // EQUATION_HPP