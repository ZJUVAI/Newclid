#include "type/point.hpp"

Point::Point(std::string name, double x, double y) : _num(PointNum(x, y)), _name(name) {}

Point::Point(std::string name, PointNum num) : _num(num), _name(name) {}

std::string Point::name() const { return _name; }

double Point::x() const { return _num.x(); }

double Point::y() const { return _num.y(); }

PointNum Point::num() const { return _num; }

std::string Point::to_string() const
{
    return _name + "(" + std::to_string(_num.x()) + "," + std::to_string(_num.y()) + ")";
}

bool Point::is_close(const Point &other) const
{
    return Numerical::close_enough(x(), other.x()) && Numerical::close_enough(y(), other.y());
}

bool Point::operator==(const Point &other) const
{
    return _name == other.name();
}

bool Point::operator<(const Point &other) const
{
    return _name < other.name();
}

bool Point::operator>(const Point &other) const
{
    return _name > other.name();
}

bool Point::operator<=(const Point &other) const
{
    return _name <= other.name();
}

bool Point::operator>=(const Point &other) const
{
    return _name >= other.name();
}

std::ostream &operator<<(std::ostream &os, const Point &pt)
{
    os << pt.name();
    return os;
}
