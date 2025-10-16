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

using namespace std;
using namespace std::chrono;

using DepGraph = map<string, pair<vector<string>, string>>;

void printProofStep(const string &goal, const DepGraph &dep_graph, unordered_set<string> &visited, int &step_num)
{
    if (visited.find(goal) != visited.end())
    {
        return;
    }

    auto it = dep_graph.find(goal);
    if (it != dep_graph.end())
    {
        const vector<string> &dependencies = it->second.first;
        const string &reason = it->second.second;
        for (const auto &dep_stmt : dependencies)
        {
            printProofStep(dep_stmt, dep_graph, visited, step_num);
        }

        step_num++;
        cout << "[" << step_num << "] " << goal << " because " << reason << endl;

        visited.insert(goal);
    }
}

void printProof(const string &goal, const DepGraph &dep_graph)
{
    unordered_set<string> visited;
    int step_num = 0;
    printProofStep(goal, dep_graph, visited, step_num);
}

int main(int argc, char *argv[])
{
    Problem problem;
    string filepath = argv[1];

    auto start_load = high_resolution_clock::now();

    problem.load_from_file(filepath);

    auto end_load = high_resolution_clock::now();
    auto duration_load = duration_cast<milliseconds>(end_load - start_load);

    cout << "------------------------------------------------------------" << endl;
    cout << "Loading time: " << duration_load.count() << " ms" << endl;
    cout << "Problem: " << problem.name() << endl;

    DDARSolver solver(&problem);

    auto start_run = high_resolution_clock::now();

    solver.run(20);

    auto end_run = high_resolution_clock::now();
    auto duration_run = duration_cast<milliseconds>(end_run - start_run);
    auto duration_total = duration_cast<seconds>(end_run - start_load);

    cout << "Finish run after " << duration_run.count() << " ms" << endl;
    cout << "Total time: " << duration_total.count() << " s" << endl;

    if (solver.is_solved())
    {
        cout << "Solved!" << endl;
    }
    else
    {
        cout << "Not solved!" << endl;
    }

    DepGraph dep_graph = solver.dependency_graph();

    // int count = 0;
    // for (const auto &[key, value] : dep_graph)
    // {
    //     count++;
    //     if (value.second.substr(0, 9) == "Numerical")
    //     {
    //         continue;
    //     }
    //     cout << "[" << count << "]" << endl;
    //     cout << "Statement: " << key << endl;
    //     cout << "  Reason: " << value.second << endl;
    //     cout << "  Dependencies: ";
    //     for (const auto &dep : value.first)
    //     {
    //         cout << dep << "; ";
    //     }
    //     cout << endl;
    // }

    for (const auto &goal : problem.goals())
    {
        cout << "--------" << endl;
        cout << "Goal: " << goal->normalize()->to_string() << endl;
        printProof(goal->normalize()->to_string(), dep_graph);
    }

    return 0;
}