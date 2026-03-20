#include "ar/linear_combination.hpp"
#include "ar/equation_index.hpp"
#include "ar/term.hpp"
#include <algorithm>

using namespace std;

LinearCombination::LinearCombination(vector<Term> terms) : _is_sorted(false)
{
    // Sort input terms and merge duplicates in one pass
    std::sort(terms.begin(), terms.end(), std::greater<Term>());

    _terms.reserve(terms.size());
    for (auto &term : terms)
    {
        if (!_terms.empty() && _terms.back() == term)
        {
            _terms.back() += term;
        }
        else
        {
            _terms.push_back(std::move(term));
        }
    }

    // Remove zero terms
    auto new_end = std::remove_if(_terms.begin(), _terms.end(),
        [](const Term& t) { return t.is_zero(); });
    _terms.erase(new_end, _terms.end());

    _is_sorted = true;
}

LinearCombination &LinearCombination::operator+=(const LinearCombination &other)
{
    if (other._terms.empty()) return *this;
    if (_terms.empty()) {
        _terms = other._terms;
        _is_sorted = other._is_sorted;
        return *this;
    }

    // Ensure both are sorted before merge
    if (!_is_sorted) {
        std::sort(_terms.begin(), _terms.end(), std::greater<Term>());
        _is_sorted = true;
    }

    // If other is not sorted, we need to sort a copy
    const std::vector<Term>* other_terms = &other._terms;
    std::vector<Term> sorted_other;
    if (!other._is_sorted) {
        sorted_other = other._terms;
        std::sort(sorted_other.begin(), sorted_other.end(), std::greater<Term>());
        other_terms = &sorted_other;
    }

    // Two-pointer merge (both vectors are in descending order)
    std::vector<Term> merged;
    merged.reserve(_terms.size() + other_terms->size());

    auto it1 = _terms.begin(), end1 = _terms.end();
    auto it2 = other_terms->begin(), end2 = other_terms->end();

    while (it1 != end1 && it2 != end2) {
        if (*it1 > *it2) {
            merged.push_back(*it1++);
        } else if (*it2 > *it1) {
            merged.push_back(*it2++);
        } else {
            // Same term, merge coefficients
            Term combined = *it1;
            combined += *it2;
            if (!combined.is_zero()) {
                merged.push_back(combined);
            }
            ++it1; ++it2;
        }
    }

    // Append remaining elements
    merged.insert(merged.end(), it1, end1);
    merged.insert(merged.end(), it2, end2);

    _terms = std::move(merged);
    _is_sorted = true;
    return *this;
}

LinearCombination LinearCombination::operator+(const LinearCombination &other) const
{
    LinearCombination res = *this;
    res += other;
    // No need to normalize - operator+= already produces normalized result
    return res;
}

LinearCombination &LinearCombination::operator-=(const LinearCombination &other)
{
    return *this += -other;
}

LinearCombination LinearCombination::operator-(const LinearCombination &other) const
{
    LinearCombination res = *this;
    res -= other;
    // No need to normalize - operator-= already produces normalized result
    return res;
}

LinearCombination &LinearCombination::operator*=(const Rational &multiplier)
{
    if (multiplier == Rational(0)) {
        _terms.clear();
        _is_sorted = true;
        return *this;
    }
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    // Rational multiplication preserves order
    return *this;
}

LinearCombination LinearCombination::operator*(const Rational &multiplier) const
{
    LinearCombination res = *this;
    res *= multiplier;
    return res;
}

LinearCombination &LinearCombination::operator*=(const Term &multiplier)
{
    if (multiplier.is_zero()) {
        _terms.clear();
        _is_sorted = true;
        return *this;
    }
    for (auto &term : _terms)
    {
        term *= multiplier;
    }
    // Term multiplication may change relative ordering, mark as unsorted
    _is_sorted = false;
    return *this;
}

LinearCombination LinearCombination::operator*(const Term &multiplier) const
{
    LinearCombination res = *this;
    res *= multiplier;
    return res;
}

LinearCombination LinearCombination::operator-() const
{
    LinearCombination res = *this;
    for (auto &term : res._terms)
    {
        term = -term;
    }
    return res;
}

void LinearCombination::normalize()
{
    // Remove zero terms
    auto new_end = std::remove_if(_terms.begin(), _terms.end(),
        [](const Term& t) { return t.is_zero(); });
    _terms.erase(new_end, _terms.end());

    // Only sort if needed (lazy sorting)
    if (!_is_sorted && _terms.size() > 1) {
        std::sort(_terms.begin(), _terms.end(), std::greater<Term>());
        _is_sorted = true;
    }
}

Term LinearCombination::gcd()
{

    if (_terms.empty())
    {
        return Term();
    }

    Term common = _terms[0];

    for (size_t i = 0; i < _terms.size(); ++i)
    {
        common = common.gcd(_terms[i]);
        if (common.is_one())
        {
            return common;
        }
    }

    return common;
}

std::vector<Term>::const_iterator LinearCombination::begin() const
{
    return _terms.begin();
}

std::vector<Term>::const_iterator LinearCombination::end() const
{
    return _terms.end();
}

ostream &operator<<(ostream &os, const LinearCombination &eq)
{
    bool first = true;
    for (const auto &term : eq.terms())
    {
        if (!first)
        {
            os << " + ";
        }
        os << term;
        first = false;
    }
    return os;
}