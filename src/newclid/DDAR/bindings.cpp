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

// Application 信息结构体
struct ApplicationInfo
{
    vector<string> premises;        // 前提
    vector<string> conclusions;     // 结论
    vector<size_t> proved_premises; // 已证明的前提索引
};

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

// 将定理字符串列表转换为 CustomRule 列表
// 每个定理字符串格式: "rule_name|premise1_type arg1 arg2...,premise2_type arg1 arg2...|conclusion1_type arg1 arg2...,conclusion2_type arg1 arg2..."
vector<CustomRule> parse_custom_theorems(const vector<string> &theorem_strings)
{
    vector<CustomRule> rules;

    for (const auto &thm_str : theorem_strings)
    {
        CustomRule rule;

        // 按 | 分割: rule_name | premises | conclusions
        size_t first_pipe = thm_str.find('|');
        size_t second_pipe = thm_str.find('|', first_pipe + 1);

        if (first_pipe == string::npos || second_pipe == string::npos)
            continue;

        rule.name = thm_str.substr(0, first_pipe);
        rule.rule = rule.name;

        string premises_str = thm_str.substr(first_pipe + 1, second_pipe - first_pipe - 1);
        string conclusions_str = thm_str.substr(second_pipe + 1);

        // 解析前提（用逗号分隔）
        stringstream premises_ss(premises_str);
        string premise;
        while (getline(premises_ss, premise, ','))
        {
            // 去除首尾空格
            premise.erase(0, premise.find_first_not_of(" \t\n\r"));
            premise.erase(premise.find_last_not_of(" \t\n\r") + 1);

            if (premise.empty())
                continue;

            // 解析单个谓词：type arg1 arg2 ...
            stringstream pred_ss(premise);
            vector<string> tokens;
            string token;
            while (pred_ss >> token)
                tokens.push_back(token);

            if (tokens.size() >= 2)
            {
                Stmt stmt;
                stmt.first = tokens[0];
                stmt.second = vector<string>(tokens.begin() + 1, tokens.end());
                rule.premises.push_back(stmt);
            }
        }

        // 解析结论（用逗号分隔）
        stringstream conclusions_ss(conclusions_str);
        string conclusion;
        while (getline(conclusions_ss, conclusion, ','))
        {
            // 去除首尾空格
            conclusion.erase(0, conclusion.find_first_not_of(" \t\n\r"));
            conclusion.erase(conclusion.find_last_not_of(" \t\n\r") + 1);

            if (conclusion.empty())
                continue;

            // 解析单个谓词：type arg1 arg2 ...
            stringstream pred_ss(conclusion);
            vector<string> tokens;
            string token;
            while (pred_ss >> token)
                tokens.push_back(token);

            if (tokens.size() >= 2)
            {
                Stmt stmt;
                stmt.first = tokens[0];
                stmt.second = vector<string>(tokens.begin() + 1, tokens.end());
                rule.conclusions.push_back(stmt);
            }
        }

        if (!rule.premises.empty() && !rule.conclusions.empty())
            rules.push_back(rule);
    }

    return rules;
}

extern "C"
{
    pair<bool, DepGraph> run_ddar(
        string name,
        vector<tuple<string, double, double>> points,
        vector<pair<string, vector<string>>> premises,
        vector<pair<string, vector<string>>> goals,
        int max_level,
        py::dict config)
    {
        // Convert Python dict to C++ map
        map<string, bool> config_map;
        for (auto item : config)
        {
            config_map[item.first.cast<string>()] = item.second.cast<bool>();
        }

        Problem problem;
        problem.load_from_data(name, points, premises, goals);

        DDARSolver solver(&problem, config_map);
        solver.run(max_level);

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

    pair<bool, DepGraph> run_ddar_with_custom_theorems(
        string name,
        vector<tuple<string, double, double>> points,
        vector<pair<string, vector<string>>> premises,
        vector<pair<string, vector<string>>> goals,
        vector<string> custom_theorem_strings,
        int max_level,
        py::dict config)
    {
        // Convert Python dict to C++ map
        map<string, bool> config_map;
        for (auto item : config)
        {
            config_map[item.first.cast<string>()] = item.second.cast<bool>();
        }

        Problem problem;
        problem.load_from_data(name, points, premises, goals);

        DDARSolver solver(&problem, config_map);

        // 添加自定义定理
        if (!custom_theorem_strings.empty())
        {
            vector<CustomRule> custom_rules = parse_custom_theorems(custom_theorem_strings);
            solver.add_custom_theorems(custom_rules);
        }

        solver.run(max_level);

        DepGraph dep_graph = solver.dependency_graph();
        return make_pair(solver.is_solved(), dep_graph);
    }

    vector<string> get_possible_goals(
        string name,
        vector<tuple<string, double, double>> points,
        vector<pair<string, vector<string>>> premises,
        py::dict config)
    {
        // Convert Python dict to C++ map
        map<string, bool> config_map;
        for (auto item : config)
        {
            config_map[item.first.cast<string>()] = item.second.cast<bool>();
        }

        Problem problem;
        problem.load_from_data(name, points, premises, {});

        DDARSolver solver(&problem, config_map);
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

    pair<vector<int>, vector<ApplicationInfo>> check_goals(
        string name,
        vector<tuple<string, double, double>> points,
        vector<pair<string, vector<string>>> premises,
        vector<pair<string, vector<string>>> goals,
        int max_level,
        py::dict config,
        bool need_applications = false)
    {
        // Convert Python dict to C++ map
        map<string, bool> config_map;
        for (auto item : config)
        {
            config_map[item.first.cast<string>()] = item.second.cast<bool>();
        }

        Problem problem;
        problem.load_from_data(name, points, premises, goals);
        DDARSolver solver(&problem, config_map);
        solver.run(max_level);

        vector<int> solved_indices;
        const auto &solver_goals = solver.goals();
        for (size_t i = 0; i < solver_goals.size(); ++i)
        {
            if (solver_goals[i]->is_proved())
            {
                solved_indices.push_back(static_cast<int>(i));
            }
        }

        vector<ApplicationInfo> pending_apps;
        if (need_applications)
        {
            for (const auto &app : solver.applications())
            {
                if (app.state() != ApplicationState::PENDING)
                {
                    continue;
                }

                ApplicationInfo info;
                vector<size_t> proved_indices;

                // 收集前提和已证明的前提索引
                for (size_t i = 0; i < app.hypotheses().size(); ++i)
                {
                    const auto *hyp = app.hypotheses()[i];
                    info.premises.push_back(hyp->statement()->to_string());
                    if (hyp->is_proved())
                    {
                        proved_indices.push_back(i);
                    }
                }

                // 收集结论
                for (const auto *conc : app.conclusions())
                {
                    info.conclusions.push_back(conc->statement()->to_string());
                }

                info.proved_premises = proved_indices;
                pending_apps.push_back(info);
            }
        }

        return make_pair(solved_indices, pending_apps);
    }
}

PYBIND11_MODULE(DDAR, m)
{
    py::class_<ApplicationInfo>(m, "ApplicationInfo")
        .def(py::init<>())
        .def_readwrite("premises", &ApplicationInfo::premises)
        .def_readwrite("conclusions", &ApplicationInfo::conclusions)
        .def_readwrite("proved_premises", &ApplicationInfo::proved_premises);

    m.def("run_ddar", &run_ddar, "Run DDAR with given problem",
          py::arg("name"),
          py::arg("points"),
          py::arg("premises"),
          py::arg("goals"),
          py::arg("max_level"),
          py::arg("config"));

    m.def("run_ddar_with_custom_theorems", &run_ddar_with_custom_theorems,
          "Run DDAR with custom theorems",
          py::arg("name"),
          py::arg("points"),
          py::arg("premises"),
          py::arg("goals"),
          py::arg("custom_theorem_strings"),
          py::arg("max_level"),
          py::arg("config"));

    m.def("get_possible_goals", &get_possible_goals,
          "Get all possible goals for a given problem",
          py::arg("name"),
          py::arg("points"),
          py::arg("premises"),
          py::arg("config"));

    m.def("check_goals", &check_goals,
          "Check which goals are solved and return their indices",
          py::arg("name"),
          py::arg("points"),
          py::arg("premises"),
          py::arg("goals"),
          py::arg("max_level"),
          py::arg("config"),
          py::arg("need_applications") = false);
}
