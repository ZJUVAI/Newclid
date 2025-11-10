#include "predicate/midpoint.hpp"
#include "predicate/cong.hpp"
#include "predicate/coll.hpp"
#include "type/point.hpp"
#include "type/dist.hpp"

using namespace std;

Midp::Midp(Point middle, Point left, Point right) : _middle(middle), _left(left), _right(right) {}

Midp::Midp(const vector<statement_arg> &args) : _middle(args[0].point), _left(args[1].point), _right(args[2].point) {}

string Midp::name() const
{
    return "midp";
}

vector<Point> Midp::points() const
{
    return {_middle, _left, _right};
}

unique_ptr<Statement> Midp::normalize() const
{
    if (_left < _right)
    {
        return clone();
    }
    return make_unique<Midp>(_right, _middle, _left);
}

bool Midp::check_nondegen() const
{
    return to_coll().check_nondegen() && !_left.is_close(_middle);
}

bool Midp::check_equations() const
{
    return to_coll().check_equations() && to_cong().check_equations();
}

vector<statement_arg> Midp::args() const
{
    return to_coll().args();
}

unique_ptr<Statement> Midp::clone() const
{
    return make_unique<Midp>(*this);
}

ostream &Midp::print(ostream &os) const
{
    return os << _middle << " is the midpoint of " << _left << _right;
}

Coll Midp::to_coll() const
{
    return Coll(_left, _middle, _right);
}

Cong Midp::to_cong() const
{
    return Cong(Dist(_left, _middle), Dist(_middle, _right));
}