#ifndef EQUATION_INDEX_HPP
#define EQUATION_INDEX_HPP

#include <ostream>

class Equation;

class LinearSystem;

class EquationIndex final
{
private:
    size_t _index;
    const LinearSystem *_system;

public:
    EquationIndex(size_t index, const LinearSystem *system) : _index(index), _system(system) {}

    size_t index() const { return _index; }

    const LinearSystem *system() const { return _system; }

    const Equation &equation() const;

    bool is_valid() const { return _system != nullptr && _index >= 0; }

    bool operator==(const EquationIndex &other) const
    {
        return _index == other._index && _system == other._system;
    }

    bool operator!=(const EquationIndex &other) const
    {
        return !(*this == other);
    }

    bool operator<(const EquationIndex &other) const
    {
        return _index < other._index;
    }

    bool operator>(const EquationIndex &other) const
    {
        return _index > other._index;
    }

    bool operator<=(const EquationIndex &other) const
    {
        return _index <= other._index;
    }

    bool operator>=(const EquationIndex &other) const
    {
        return _index >= other._index;
    }
};

inline std::ostream &operator<<(std::ostream &os, const EquationIndex &index)
{
    os << "<" << index.index() << ">";
    return os;
}

#endif // EQUATION_INDEX_HPP