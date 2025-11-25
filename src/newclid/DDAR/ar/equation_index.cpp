#include "ar/equation_index.hpp"
#include "ar/linear_system.hpp"
#include "ar/equation.hpp"

using namespace std;

const Equation &EquationIndex::equation() const
{
    return _system->at(_index);
}