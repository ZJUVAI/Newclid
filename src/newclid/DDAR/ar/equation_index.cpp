#include "ar/equation_index.hpp"
#include "ar/linear_system.hpp"
#include "ar/equation.hpp"
#include "type/distlog.hpp"

using namespace std;

template <typename VarT>
const Equation<VarT> &EquationIndex<VarT>::equation() const
{
    return _system->at(*this);
}

template class EquationIndex<Slope>;
template class EquationIndex<Dist>;
template class EquationIndex<DistLog>;