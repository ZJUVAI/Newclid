#ifndef LINEAR_SYSTEM_HPP
#define LINEAR_SYSTEM_HPP

#include <vector>
#include <set>
#include <unordered_map>
#include <map>
#include "ar/equation.hpp"
#include "ar/equation_index.hpp"
#include "typedef.hpp"

class Proof;

template <typename VarT>
class ReducedEquation;

template <typename VarT>
class LinearSystem final
{
public:
    using EquationType = Equation<VarT>;
    using IndexType = EquationIndex<VarT>;
    using VarType = VarT;
    using LinearCombinationType = Equation<EquationIndex<VarT>>;
    using RHSType = typename EquationTraits<VarT>::RHSType;
    using EchelonFormType = std::unordered_map<VarType, LinearCombinationType>;

private:
    std::vector<std::pair<EquationType, Proof *>> _equations;
    EchelonFormType _echelon_form;
    std::set<VarType> _found_variables;
    std::map<VarType, std::set<VarType>> _pivot_by_next;

public:
    LinearSystem() = default;
    void reduce_next(LinearCombinationType &e);
    void add_reduced_equation(Proof *pf);
    const EquationType &at(IndexType index) const;
    const std::pair<EquationType, Proof *> &pair_at(IndexType index) const;
    size_t size() const;
    const EchelonFormType &echelon_form() const
    {
        return _echelon_form;
    }
    const std::map<VarType, std::set<VarType>> &pivot_by_next()
    {
        return _pivot_by_next;
    }
    std::set<VarType> new_found_variables() const;
    void clear_new_found_variables();
};

#endif // LINEAR_SYSTEM_HPP