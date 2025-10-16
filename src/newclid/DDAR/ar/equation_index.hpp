#ifndef EQUATION_INDEX_HPP
#define EQUATION_INDEX_HPP

#include <ostream>

template <typename VarT>
class Equation;

template <typename VarT>
class LinearSystem;

template <typename VarT>
class EquationIndex final
{
private:
    size_t _index;
    const LinearSystem<VarT> *_system;

public:
    EquationIndex(size_t index, const LinearSystem<VarT> *system) : _index(index), _system(system) {}

    size_t index() const { return _index; }

    const LinearSystem<VarT> *system() const { return _system; }

    const Equation<VarT> &equation() const;

    bool operator==(const EquationIndex<VarT> &other) const
    {
        return _index == other._index && _system == other._system;
    }

    bool operator!=(const EquationIndex<VarT> &other) const
    {
        return !(*this == other);
    }

    bool operator<(const EquationIndex<VarT> &other) const
    {
        return _index < other._index;
    }

    bool operator>(const EquationIndex<VarT> &other) const
    {
        return _index > other._index;
    }

    bool operator<=(const EquationIndex<VarT> &other) const
    {
        return _index <= other._index;
    }

    bool operator>=(const EquationIndex<VarT> &other) const
    {
        return _index >= other._index;
    }
};

template <typename VarT>
std::ostream &operator<<(std::ostream &os, const EquationIndex<VarT> &index)
{
    os << "(" << index.index() << ")";
    return os;
}

#endif // EQUATION_INDEX_HPP