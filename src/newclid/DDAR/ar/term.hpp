#ifndef TERM_HPP
#define TERM_HPP

#include "ar/term_arg.hpp"
#include "type/rational.hpp"
#include <iostream>
#include <map>
#include <vector>

class ObjectTable;
class Object;

class Term
{
private:
    mutable std::map<TermArg, int> _vars;
    mutable std::map<Object *, int> _actual_vars;
    mutable size_t _version{SIZE_MAX};
    Rational _coeff;
    ObjectTable *_table{nullptr};

public:
    // Constructors
    Term(const std::vector<TermArg> &vars, const Rational &coeff, ObjectTable *table = nullptr);
    Term(const TermArg &var, const Rational &coeff, ObjectTable *table = nullptr);
    Term(const Rational &coeff, ObjectTable *table = nullptr);
    Term(const std::vector<TermArg> &vars, ObjectTable *table = nullptr);
    Term(const TermArg &var, ObjectTable *table = nullptr);
    Term(ObjectTable *table = nullptr);

    // Accessors
    Rational coeff() const { return _coeff; }

    // Operations
    Term gcd(Term &other) const;
    void normalize();
    void update() const;
    int degree() const;
    double to_double() const;
    std::string to_string() const;

    // Predicates
    bool is_zero() const { return _coeff == 0; }
    bool is_one() const { return _vars.empty(); }
    bool is_pi() const { return _vars.size() == 1 && _vars.begin()->first.type() == TermArg::ArgType::Pi; }
    bool contain(const Term &other) const;

    // Arithmetic operators
    Term operator*(const Rational &multiplier) const;
    Term &operator*=(const Rational &multiplier);
    Term operator/(const Rational &divisor) const;
    Term &operator/=(const Rational &divisor);

    Term operator*(const Term &other) const;
    Term &operator*=(const Term &other);
    Term operator/(const Term &other) const;
    Term &operator/=(const Term &other);

    Term operator+(const Term &other) const;
    Term &operator+=(const Term &other);
    Term operator-() const;

    // Comparison operators
    bool operator==(const Term &other) const;
    bool operator!=(const Term &other) const;
    bool operator<(const Term &other) const;
    bool operator>(const Term &other) const;
    bool operator<=(const Term &other) const;
    bool operator>=(const Term &other) const;

    // Hash
    size_t hash() const;
};

std::ostream &operator<<(std::ostream &os, const Term &term);

namespace std
{
    template <>
    struct hash<Term>
    {
        std::size_t operator()(const Term &term) const noexcept
        {
            return term.hash();
        }
    };
}

#endif // TERM_HPP