#include "type/point.hpp"
#include "type/slope.hpp"
#include "matcher.hpp"
#include "theorem.hpp"
#include "problem.hpp"
#include "solver/ddar.hpp"
#include <iostream>
#include <map>
#include <vector>
#include <chrono>
#include <unordered_set>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace std;

using StatementTokens = vector<string>;
using DepGraph = vector<tuple<StatementTokens, vector<StatementTokens>, string>>;

extern "C"
{
    pair<bool, DepGraph> run_ddar(string name, vector<tuple<string, double, double>> points, vector<pair<string, vector<string>>> premises, vector<pair<string, vector<string>>> goals)
    {
        Problem problem;
        problem.load_from_data(name, points, premises, goals);

        // for (auto &p : problem.points())
        // {
        //     cout << "point " << p.name() << " " << p.x() << " " << p.y() << endl;
        // }

        // for (auto &stmt : problem.hypotheses())
        // {
        //     cout << "premise " << stmt->to_string() << endl;
        // }

        // for (auto &stmt : problem.goals())
        // {
        //     cout << "goal " << stmt->to_string() << endl;
        // }

        cout << "------------------------------------------------------------" << endl;
        cout << "Problem: " << name << endl;

        DDARSolver solver(&problem);
        solver.run(100);

        if (solver.is_solved())
        {
            cout << "Solved!" << endl;
        }
        else
        {
            cout << "Not solved!" << endl;
        }

        DepGraph dep_graph = solver.dependency_graph();

        return make_pair(solver.is_solved(), dep_graph);
    }
}

PYBIND11_MODULE(DDAR, m)
{
    m.def("run_ddar", &run_ddar, "Run DDAR with given problem");
}