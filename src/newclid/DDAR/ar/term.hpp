#ifndef TERM_HPP
#define TERM_HPP

#include "typedef.hpp"
#include <iostream>
#include <vector>
#include <map>

class Term
{
private:
    std::map<term_arg, int> _vars;
    Rational _coeff;

public:
    Term(const std::vector<term_arg> &vars, const Rational &coeff);

    Term(const term_arg &var, const Rational &coeff);

    Term(const Rational &coeff);

    Term(const std::vector<term_arg> &vars);

    Term(const term_arg &var);

    Term();

    Rational coeff() const { return _coeff; }

    Term gcd(const Term &other) const;

    Term operator*(const Rational &multiplier) const;

    Term operator/(const Rational &divisor) const;

    Term &operator*=(const Rational &multiplier);

    Term &operator/=(const Rational &divisor);

    Term operator*(const Term &other) const;

    Term operator/(const Term &other) const;

    Term &operator*=(const Term &other);

    Term &operator/=(const Term &other);

    Term operator+(const Term &other) const;

    Term &operator+=(const Term &other);

    Term operator-() const;

    void normalize();

    void round(); // only used for pi

    int degree() const;

    double to_double() const;

    std::string to_string() const;

    bool is_zero() const { return _coeff == 0; }

    bool is_one() const { return _vars.empty(); }

    bool is_pi() const { return _vars.size() == 1 && _vars.begin()->first.type == term_arg::Type::PiType; }

    bool contain(const Term &other) const;

    bool operator==(const Term &other) const;

    bool operator<(const Term &other) const;

    bool operator>(const Term &other) const;

    bool operator<=(const Term &other) const;

    bool operator>=(const Term &other) const;

    bool operator!=(const Term &other) const;
};

std::ostream &operator<<(std::ostream &os, const Term &term);

namespace std
{
    template <>
    struct hash<Term>
    {
        size_t operator()(const Term &t) const noexcept
        {
            return std::hash<std::string>{}(t.to_string());
        }
    };
}

#endif // TERM_HPP