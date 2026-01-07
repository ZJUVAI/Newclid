#include "predicate/pappus.hpp"
#include <set>
#include <memory>

using namespace std;

Pappus::Pappus(const Coll &left, const Coll &middle, const Coll &right) : _left(left), _middle(middle), _right(right) {}

Pappus::Pappus(const vector<statement_arg> &args) : _left(Coll(args[0].point, args[1].point, args[2].point)), _middle(Coll(args[3].point, args[4].point, args[5].point)), _right(Coll(args[6].point, args[7].point, args[8].point)) {}

string Pappus::name() const
{
    return "pappus";
}

vector<Point> Pappus::points() const
{
    return {_left.a(), _left.b(), _left.c(), _middle.a(), _middle.b(), _middle.c(), _right.a(), _right.b(), _right.c()};
}

unique_ptr<Statement> Pappus::normalize() const
{
    auto all = permutations();
    return make_unique<Pappus>(*min_element(all.begin(), all.end()));
}

unique_ptr<Statement> Pappus::replace(Point p, Point q) const
{
    auto left_ptr = _left.replace(p, q);
    auto middle_ptr = _middle.replace(p, q);
    auto right_ptr = _right.replace(p, q);
    return make_unique<Pappus>(
        static_cast<const Coll &>(*left_ptr),
        static_cast<const Coll &>(*middle_ptr),
        static_cast<const Coll &>(*right_ptr));
}

bool Pappus::check_nondegen() const
{
    if (!_left.check_nondegen() || !_middle.check_nondegen() || !_right.check_nondegen())
        return false;
    vector<Point> pts = points();
    set<Point> s(pts.begin(), pts.end());
    return s.size() == 9;
}

bool Pappus::check_equations() const
{
    if (!_left.check_equations() || !_middle.check_equations() || !_right.check_equations())
        return false;
    return coll_ab().check_equations() && coll_ba().check_equations() && coll_bc().check_equations() && coll_cb().check_equations() && coll_ca().check_equations() && coll_ac().check_equations();
}

vector<statement_arg> Pappus::args() const
{
    return {_left.a(), _left.b(), _left.c(), _middle.a(), _middle.b(), _middle.c(), _right.a(), _right.b(), _right.c()};
}

unique_ptr<Statement> Pappus::clone() const
{
    return make_unique<Pappus>(*this);
}

ostream &Pappus::print(ostream &os) const
{
    return os << "pappus(" << _left << ", " << _middle << ", " << _right << ")";
}

vector<Pappus> Pappus::permutations() const
{
    vector<Pappus> res;
    auto per_left = _left.permutations();
    auto per_middle = _middle.permutations();
    auto per_right = _right.permutations();
    for (size_t i = 0; i < per_left.size(); i++)
    {
        res.push_back(Pappus(per_left[i], per_middle[i], per_right[i]));
        res.push_back(Pappus(per_left[i], per_right[i], per_middle[i]));
        res.push_back(Pappus(per_right[i], per_left[i], per_middle[i]));
        res.push_back(Pappus(per_right[i], per_middle[i], per_left[i]));
        res.push_back(Pappus(per_middle[i], per_left[i], per_right[i]));
    }
    return res;
}

bool Pappus::operator==(const Pappus &other) const
{
    return _left == other._left && _middle == other._middle && _right == other._right;
}

bool Pappus::operator!=(const Pappus &other) const
{
    return !(*this == other);
}

bool Pappus::operator<(const Pappus &other) const
{
    if (_left == other._left)
    {
        if (_middle == other._middle)
        {
            return _right < other._right;
        }
        return _middle < other._middle;
    }
    return _left < other._left;
}

bool Pappus::operator>(const Pappus &other) const
{
    return other < *this;
}

bool Pappus::operator<=(const Pappus &other) const
{
    return !(*this > other);
}

bool Pappus::operator>=(const Pappus &other) const
{
    return !(*this < other);
}

Coll Pappus::coll_ab() const
{
    return Coll(_left.a(), _middle.c(), _right.b());
}

Coll Pappus::coll_ba() const
{
    return Coll(_left.b(), _middle.c(), _right.a());
}

Coll Pappus::coll_bc() const
{
    return Coll(_left.b(), _middle.a(), _right.c());
}

Coll Pappus::coll_cb() const
{
    return Coll(_left.c(), _middle.a(), _right.b());
}

Coll Pappus::coll_ac() const
{
    return Coll(_left.a(), _middle.b(), _right.c());
}

Coll Pappus::coll_ca() const
{
    return Coll(_left.c(), _middle.b(), _right.a());
}