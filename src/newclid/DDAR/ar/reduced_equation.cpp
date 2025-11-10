#include "ar/reduced_equation.hpp"

#include "ar/equation.hpp"
#include "ar/linear_system.hpp"

using namespace std;

template <typename VarT>
ReducedEquation<VarT>::ReducedEquation(const EquationType &equation, const LinearSystem<VarT> *system)
    : _original_equation(equation),
      _system(system),
      _linear_combination(),
      _remainder(equation)
{
}

template <typename VarT>
void ReducedEquation<VarT>::reduce()
{
    while (!_remainder.lhs().empty())
    {
        auto &[var, coeff] = *_remainder.lhs().begin();
        auto echelon_itr = _system->echelon_form().find(var);
        if (echelon_itr != _system->echelon_form().end())
        {
            const LinearCombinationType pivot = echelon_itr->second;
            _linear_combination += pivot * coeff;
            _remainder -= pivot.rhs() * coeff;
        }
        else
        {
            break;
        }
    }
}

template <typename VarT>
bool ReducedEquation<VarT>::is_solved() const
{
    return _remainder.is_empty();
}

template class ReducedEquation<Slope>;
template class ReducedEquation<DistLog>;
template class ReducedEquation<Product>;