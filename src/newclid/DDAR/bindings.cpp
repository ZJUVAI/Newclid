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
#include <tuple>
#include <string>
#include <sstream>
#include <unordered_set>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace std;

using StatementTokens = vector<string>;
using DepGraph = vector<tuple<StatementTokens, vector<StatementTokens>, string>>;

std::string join(const StatementTokens &tokens)
{
    std::ostringstream oss;
    for (size_t i = 0; i < tokens.size(); ++i)
    {
        if (i != 0)
            oss << " "; // 添加空格分隔符
        oss << tokens[i];
    }
    return oss.str();
}

extern "C"
{
    pair<bool, DepGraph> run_ddar(string name, vector<tuple<string, double, double>> points, vector<pair<string, vector<string>>> premises, vector<pair<string, vector<string>>> goals, int max_level = 500, bool log_enabled = false, bool exp_enabled = false)
    {
        Problem problem;
        problem.load_from_data(name, points, premises, goals);
        // auto t1 = std::chrono::steady_clock::now();
        // std::cout << "load : "
        //         << std::chrono::duration<double, std::milli>(t1 - t0).count()
        //         << " ms" << endl;

        // 输出实际输入，用于 main.cpp 测试
        // std::cout << "=== INPUT DUMP ===" << std::endl;
        // std::cout << "name: " << name << std::endl;
        // std::cout << "points:" << std::endl;
        // for (const auto &p : points)
        //     std::cout << "  " << get<0>(p) << " " << get<1>(p) << " " << get<2>(p) << std::endl;
        // std::cout << "premises:" << std::endl;
        // for (const auto &pr : premises) {
        //     std::cout << "  " << pr.first;
        //     for (const auto &a : pr.second) std::cout << " " << a;
        //     std::cout << std::endl;
        // }
        // std::cout << "goals:" << std::endl;
        // for (const auto &g : goals) {
        //     std::cout << "  " << g.first;
        //     for (const auto &a : g.second) std::cout << " " << a;
        //     std::cout << std::endl;
        // }
        // std::cout << "=== END INPUT DUMP ===" << std::endl;


        // t0 = std::chrono::steady_clock::now();
        DDARSolver solver(&problem, log_enabled, exp_enabled);
        // t1 = std::chrono::steady_clock::now();
        // std::cout << "build : "
        //         << std::chrono::duration<double, std::milli>(t1 - t0).count()
        //         << " ms" << endl;
        solver.run(max_level);
        // auto t2 = std::chrono::steady_clock::now();
        // std::cout << "run : "
        //         << std::chrono::duration<double, std::milli>(t2 - t1).count()
        //         << " ms" << endl;

        // if (solver.is_solved())
        // {
        //     cout << "Solved!" << endl;
        // }
        // else
        // {
        //     cout << "Not solved!" << endl;
        // }

        DepGraph dep_graph = solver.dependency_graph();

        // for (const auto &tupleElem : dep_graph)
        // {
        //     const StatementTokens &tokens = std::get<0>(tupleElem);
        //     const std::vector<StatementTokens> &dependencies = std::get<1>(tupleElem);
        //     const std::string &reason = std::get<2>(tupleElem);

        //     if (reason == "Numerical Check" || reason == "Trivial")
        //     {
        //         continue;
        //     }

        //     std::cout << "Statement: " << join(tokens) << endl;

        //     std::cout << "Dependencies:" << endl;
        //     for (const auto &dep : dependencies)
        //     {
        //         std::cout << "  - " << join(dep) << endl;
        //     }

        //     std::cout << "Reason: " << reason << endl;
        //     std::cout << "---------------------------------------\n";
        // }

        // solver.print_equations();

        return make_pair(solver.is_solved(), dep_graph);
    }

    vector<string> get_possible_goals(string name, vector<tuple<string, double, double>> points, vector<pair<string, vector<string>>> premises)
    {
        Problem problem;
        problem.load_from_data(name, points, premises, {});

        DDARSolver solver(&problem);
        solver.run(500);

        vector<string> possible_goals;

        for (const auto &app : solver.applications())
        {
            if (app.state() != ApplicationState::PENDING)
            {
                continue;
            }
            for (const auto &c : app.conclusions())
            {
                if (c->statement()->name() == "secant" || c->is_proved())
                {
                    continue;
                }
                possible_goals.push_back(c->statement()->to_string());
            }
        }
        std::sort(possible_goals.begin(), possible_goals.end());
        auto it = std::unique(possible_goals.begin(), possible_goals.end());
        possible_goals.erase(it, possible_goals.end());
        return possible_goals;
    }
}

PYBIND11_MODULE(DDAR, m)
{
    m.def("run_ddar", &run_ddar, "Run DDAR with given problem");
    m.def("get_possible_goals", &get_possible_goals, "Get all possible goals for a given problem");
}