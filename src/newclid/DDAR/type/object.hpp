#ifndef OBJECT_HPP
#define OBJECT_HPP

#include "predicate/statement.hpp"
#include "type/point.hpp"
#include <set>
#include <vector>
#include <map>

class Proof;

class Object
{
private:
    std::set<Point> _points;
    std::map<Point, std::vector<Proof *>> _dependency;

public:
    Object(std::set<Point> points);

    Object(std::vector<Point> points);

    void add_point(Point &pt, std::vector<Proof *> reason);

    void merge(Object &other, std::vector<Proof *> reason);

    std::vector<Point> points() const;

    double to_double() const { return 0.0; }
};

#endif // OBJECT_HPP