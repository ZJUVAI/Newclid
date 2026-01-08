#include "type/object.hpp"
#include "solver/proof.hpp"

using namespace std;

Object::Object(set<Point> points) : _points(points)
{
    for (const auto &pt : _points)
    {
        _dependency[pt];
    }
}

Object::Object(vector<Point> points) : _points()
{
    _points.insert(points.begin(), points.end());
    for (const auto &pt : _points)
    {
        _dependency[pt];
    }
}

void Object::add_point(Point &pt, vector<Proof *> reason)
{
    auto [it, inserted] = _points.insert(pt);
    if (inserted)
    {
        _dependency[pt] = move(reason);
    }
}

void Object::merge(Object &other, vector<Proof *> reason)
{
    for (const Point &pt : other._points)
    {
        auto [it, inserted] = _points.insert(pt);
        if (inserted)
        {
            vector<Proof *> merged_reason = reason;

            auto other_dep_it = other._dependency.find(pt);
            if (other_dep_it != other._dependency.end())
            {
                merged_reason.insert(merged_reason.end(),
                                     other_dep_it->second.begin(),
                                     other_dep_it->second.end());
            }

            _dependency[pt] = move(merged_reason);
        }
    }
}

vector<Point> Object::points() const
{
    return vector<Point>(_points.begin(), _points.end());
}