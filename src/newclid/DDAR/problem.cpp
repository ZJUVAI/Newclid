#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include "problem.hpp"

#include "predicate/statement.hpp"
#include "predicate/aconst.hpp"
#include "predicate/circumcenter.hpp"
#include "predicate/coll.hpp"
#include "predicate/cong.hpp"
#include "predicate/congruent_triangles.hpp"
#include "predicate/cyclic.hpp"
#include "predicate/eqangle.hpp"
#include "predicate/eqratio.hpp"
#include "predicate/midpoint.hpp"
#include "predicate/orthocenter.hpp"
#include "predicate/para.hpp"
#include "predicate/perp.hpp"
#include "predicate/rconst.hpp"
#include "predicate/similar_triangles.hpp"
#include "predicate/thales.hpp"
#include "type/angle.hpp"
#include "type/dist.hpp"
#include "type/point.hpp"
#include "type/rational.hpp"
#include "type/slope.hpp"
#include "type/triangle.hpp"

using namespace std;

void Problem::clear()
{
    this->_points.clear();
    this->_hypotheses.clear();
    this->_goals.clear();
    this->_name.clear();
}

void Problem::add_point(const string &name, double x, double y)
{
    Point p(name, x, y);
    _points.push_back(p);
    sort(_points.begin(), _points.end());
    return;
}

void Problem::set_name(const string &name)
{
    _name = name;
}

void Problem::add_hypothesis(unique_ptr<Statement> &&p)
{
    _hypotheses.push_back(move(p));
}

void Problem::add_goal(unique_ptr<Statement> &&p)
{
    _goals.push_back(move(p));
}

Point &Problem::point(size_t index)
{
    return _points[index];
}

vector<Point> Problem::points()
{
    return _points;
}

string Problem::name()
{
    return _name;
}

const vector<unique_ptr<Statement>> &Problem::hypotheses()
{
    return _hypotheses;
}

const vector<unique_ptr<Statement>> &Problem::goals()
{
    return _goals;
}

size_t Problem::num_points() const
{
    return _points.size();
}

Point Problem::find_point(const string &name) const
{
    for (auto &p : _points)
    {
        if (p.name() == name)
        {
            return p;
        }
    }
    throw runtime_error("Point not found");
}

void Problem::load_from_file(const string &filename)
{
    this->clear();

    this->set_name(filename.substr(filename.find_last_of("\\/") + 1));

    ifstream file(filename);
    if (!file.is_open())
    {
        cout << "Failed to open file " << filename << endl;
        return;
    }

    string line;
    while (getline(file, line))
    {
        stringstream ss(line);
        string cmd;
        ss >> cmd;
        if (cmd == "point")
        {
            double x, y;
            string name;
            ss >> name >> x >> y;
            this->add_point(name, x, y);
        }
        else if (cmd == "premise" || cmd == "assume")
        {
            string type;
            string arg;
            vector<string> args;
            ss >> type;
            while (ss >> arg)
            {
                args.push_back(arg);
            }
            auto p = create_statement(type, args);
            this->add_hypothesis(move(p));
        }
        else if (cmd == "goal" || cmd == "prove")
        {
            string type;
            string arg;
            vector<string> args;
            ss >> type;
            while (ss >> arg)
            {
                args.push_back(arg);
            }
            auto p = create_statement(type, args);
            this->add_goal(move(p));
        }
        else
        {
            cout << "Unknown command: " << cmd << endl;
            break;
        }
    }

    file.close();
}

void Problem::load_from_data(const string name, vector<tuple<string, double, double>> points, vector<pair<string, vector<string>>> premises, vector<pair<string, vector<string>>> goals)
{
    this->clear();

    this->set_name(name);

    for (auto &p : points)
    {
        this->add_point(get<0>(p), get<1>(p), get<2>(p));
    }

    for (auto &p : premises)
    {
        auto s = create_statement(p.first, p.second);
        this->add_hypothesis(move(s));
    }

    for (auto &p : goals)
    {
        auto s = create_statement(p.first, p.second);
        this->add_goal(move(s));
    }

    return;
}

unique_ptr<Statement> Problem::create_statement(const string &type, const vector<string> &args) const
{
    if (type == "aconst")
    {
        if (args.size() == 4)
        {
            Point p1 = this->find_point(args[0]);
            Point p2 = this->find_point(args[1]);
            Point p3 = this->find_point(args[2]);
            long long p = stoll(args[3].substr(0, args[3].find('/')));
            long long q = stoll(args[3].substr(args[3].find('/') + 1));
            Rational a = Rational(p, q);
            return make_unique<AConst>(Angle(p1, p2, p3), a);
        }
        else if (args.size() == 5)
        {
            Point p1 = this->find_point(args[0]);
            Point p2 = this->find_point(args[1]);
            Point p3 = this->find_point(args[2]);
            Point p4 = this->find_point(args[3]);
            long long p = stoll(args[4].substr(0, args[4].find('/')));
            long long q = stoll(args[4].substr(args[4].find('/') + 1));
            Rational a = Rational(p, q);
            return make_unique<AConst>(Angle(p1, p2, p3, p4), a);
        }
        throw runtime_error("Invalid number of arguments for " + type);
    }
    else if (type == "circle")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<CircumCenter>(p1, Triangle(p2, p3, p4));
    }
    else if (type == "coll")
    {
        if (args.size() != 3)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        return make_unique<Coll>(p1, p2, p3);
    }
    else if (type == "cong")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<Cong>(Dist(p1, p2), Dist(p3, p4));
    }
    else if (type == "contri")
    {
        if (args.size() != 6)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        return make_unique<CongruentTriangles>(Triangle(p1, p2, p3), Triangle(p4, p5, p6), true);
    }
    else if (type == "contrir")
    {
        if (args.size() != 6)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        return make_unique<CongruentTriangles>(Triangle(p1, p2, p3), Triangle(p4, p5, p6), false);
    }
    else if (type == "cyclic")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<Cyclic>(p1, p2, p3, p4);
    }
    else if (type == "eqangle")
    {
        if (args.size() == 6)
        {
            Point p1 = this->find_point(args[0]);
            Point p2 = this->find_point(args[1]);
            Point p3 = this->find_point(args[2]);
            Point p4 = this->find_point(args[3]);
            Point p5 = this->find_point(args[4]);
            Point p6 = this->find_point(args[5]);
            return make_unique<EqAngle>(Angle(p1, p2, p3), Angle(p4, p5, p6));
        }
        else if (args.size() == 8)
        {
            Point p1 = this->find_point(args[0]);
            Point p2 = this->find_point(args[1]);
            Point p3 = this->find_point(args[2]);
            Point p4 = this->find_point(args[3]);
            Point p5 = this->find_point(args[4]);
            Point p6 = this->find_point(args[5]);
            Point p7 = this->find_point(args[6]);
            Point p8 = this->find_point(args[7]);
            return make_unique<EqAngle>(p1, p2, p3, p4, p5, p6, p7, p8);
        }
        throw runtime_error("Invalid number of arguments for " + type);
    }
    else if (type == "eqratio")
    {
        if (args.size() != 8)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        Point p7 = this->find_point(args[6]);
        Point p8 = this->find_point(args[7]);
        return make_unique<EqRatio>(Dist(p1, p2), Dist(p3, p4), Dist(p5, p6), Dist(p7, p8));
    }
    else if (type == "midp")
    {
        if (args.size() != 3)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        return make_unique<Midp>(p1, p2, p3);
    }
    else if (type == "orthocenter")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<OrthoCenter>(p1, Triangle(p2, p3, p4));
    }
    else if (type == "para")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<Para>(Slope(p1, p2), Slope(p3, p4));
    }
    else if (type == "perp")
    {
        if (args.size() != 4)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        return make_unique<Perp>(Slope(p1, p2), Slope(p3, p4));
    }
    else if (type == "rconst")
    {
        if (args.size() != 5)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        size_t slash_pos = args[4].find('/');
        long long p = 0, q = 0;
        if (slash_pos != string::npos)
        {
            p = stoll(args[4].substr(0, slash_pos));
            q = stoll(args[4].substr(slash_pos + 1));
        }
        else
        {
            p = stoll(args[4]);
            q = 1;
        }
        Rational a = Rational(p, q);
        return make_unique<RConst>(Dist(p1, p2), Dist(p3, p4), a);
    }
    else if (type == "simtri")
    {
        if (args.size() != 6)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        return make_unique<SimilarTriangles>(Triangle(p1, p2, p3), Triangle(p4, p5, p6), true);
    }
    else if (type == "simtrir")
    {

        if (args.size() != 6)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        return make_unique<SimilarTriangles>(Triangle(p1, p2, p3), Triangle(p4, p5, p6), false);
    }
    else if (type == "thales")
    {
        if (args.size() != 6)
        {
            throw runtime_error("Invalid number of arguments for " + type);
        }
        Point p1 = this->find_point(args[0]);
        Point p2 = this->find_point(args[1]);
        Point p3 = this->find_point(args[2]);
        Point p4 = this->find_point(args[3]);
        Point p5 = this->find_point(args[4]);
        Point p6 = this->find_point(args[5]);
        return make_unique<Thales>(Coll(p1, p2, p3), Coll(p4, p5, p6));
    }
    else
    {
        throw runtime_error(type + " is not supported yet");
    }
}