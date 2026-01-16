#include "solver/ddar.hpp"
#include "problem.hpp"
#include "solver/application.hpp"
#include "solver/proof.hpp"
#include "matcher.hpp"
#include <vector>
#include <map>
#include <string>
#include <iostream>
#include <type_traits>
#include <cmath>
#include <chrono>

using namespace std;

DDARSolver::DDARSolver(Problem *problem, bool log_enabled, bool exp_enabled) : _problem(problem), _log_enabled(log_enabled), _exp_enabled(exp_enabled)
{
    // cout << "匹配定理" << endl;
    Matcher matcher(problem, _goals.empty());
    for (const auto &thm : matcher.theorems())
    {
        insert_application(thm.clone());
    }

    // cout << "添加前提条件" << endl;
    for (const auto &hyp : problem->hypotheses())
    {
        this->insert_statement(hyp->normalize())->prove_by_assumption();
        // cout << hyp->to_string() << "已添加" << endl;
    }

    if (!problem->goals().empty())
    {
        // cout << "添加目标" << endl;
        for (const auto &goal : problem->goals())
        {
            _goals.push_back(this->insert_statement(goal));
            // cout << goal->to_string() << "已添加" << endl;
        }
    }

    for (const auto &stmt : matcher.stmts())
    {
        _ars.push_back(this->insert_statement(stmt));
    }
}

bool DDARSolver::run_level(const Point &max_pt)
{
    size_t num_stmts = _checked_statements.size();
    _level++;

    // size_t call_count = 0;
    // double total_advance_time_ms = 0.0;

    size_t const n = _applications.size();
    for (size_t i = 0; i < n; i++)
    {
        if (_applications[i].max_point() <= max_pt && _applications[i].state() == ApplicationState::PENDING)
        {
            // auto t_start = std::chrono::steady_clock::now();
            advance_theorem(i);
            // auto t_end = std::chrono::steady_clock::now();

            // double ms = std::chrono::duration<double, std::micro>(t_end - t_start).count() / 1000.0;

            // call_count++;
            // total_advance_time_ms += ms;
        }
    }

    // ────────────────────────────────────────────────
    // 你可以选择只在有调用时才打印，避免太多0行
    // if (call_count > 0)
    // {
    //     std::cout << "Level " << _level << " | "
    //               << "advance_theorem calls: " << call_count
    //               << " | total time: " << total_advance_time_ms << " ms"
    //               << " | avg: " << (call_count ? total_advance_time_ms / call_count : 0.0) << " ms/call"
    //               << endl;
    // }
    // ────────────────────────────────────────────────

    // 後面原有的 goals 部分保持不變 ...
    if (!_problem->goals().empty())
    {
        bool res = true;
        for (auto &goal : _goals)
        {
            if (!goal->is_proved())
            {
                goal->ar(_level);
                if (!goal->is_proved())
                {
                    res = false;
                }
            }
        }
        _solved = res;
    }

    return num_stmts < _checked_statements.size();
}

bool DDARSolver::run(size_t max_levels)
{
    bool has_goal = !_problem->goals().empty();

    if (has_goal)
    {
        for (Point const &pt : _problem->points())
        {
            for (size_t i = 0; i < max_levels; ++i)
            {
                if (!run_level(pt))
                {
                    break;
                }

                if (has_goal && _solved)
                {
                    return _solved;
                }
            }
        }
    }
    else
    {
        for (size_t i = 0; i < max_levels; ++i)
        {
            if (!run_level(_problem->points().back()))
            {
                break;
            }

            if (has_goal && _solved)
            {
                return _solved;
            }
        }
        bool changed = true;
        while (changed)
        {
            changed = false;
            for (auto it = _ars.begin(); it != _ars.end();)
            {
                auto &goal = *it;
                if (goal->is_proved())
                {
                    it = _ars.erase(it);
                    changed = true;
                }
                else
                {
                    goal->ar(_level);
                    if (goal->is_proved())
                    {
                        it = _ars.erase(it);
                        changed = true;
                    }
                    else
                    {
                        ++it;
                    }
                }
            }
        }

        _solved = true;
    }

    return _solved;
}

void DDARSolver::advance_theorem(size_t index)
{
    auto &app = _applications[index];
    if (app.state() != ApplicationState::PENDING)
    {
        return;
    }

    app.advance_proof(_level);
    if (app.state() == ApplicationState::PROVED)
    {
        for (auto *p : app.conclusions())
        {
            establish_statement(p, index);
        }
    }
}

void DDARSolver::insert_application(Theorem thm)
{
    if (!thm.check_numerically())
    {
        cout << thm.name() << endl;
        throw runtime_error("Wrong theorem!!");
    }
    _applications.emplace_back(this, move(thm));
}

Proof *DDARSolver::insert_statement(const unique_ptr<Statement> &p)
{
    auto val = p->normalize();
    auto key = val->to_string();
    auto [it, success] = _statement_proofs.insert({key, std::make_unique<Proof>(this, std::move(val))});
    if (success)
    {
        it->second->initial();
    }
    return it->second.get();
}

vector<tuple<vector<string>, vector<vector<string>>, string>> DDARSolver::dependency_graph() const
{
    vector<tuple<vector<string>, vector<vector<string>>, string>> res;

    for (const auto &pf : _checked_statements)
    {
        if (!pf->is_proved())
        {
            cout << "?????" << endl;
            continue;
        }
        // if (pf->state() == ProofState::PROVED_AR)
        // {
        //     pf->print_equations();
        // }
        vector<vector<string>> deps;
        // bool flag = false;
        for (const auto &dep : pf->get_dependencies())
        {
            deps.push_back(dep->statement()->normalize()->to_tokens());
        }
        res.push_back({pf->statement()->normalize()->to_tokens(), deps, pf->reason()});
    }

    return res;
}

size_t DDARSolver::num_applications() const
{
    return _applications.size();
}

size_t DDARSolver::push_established_statement(Proof *pf)
{
    size_t const index = _checked_statements.size();
    _checked_statements.push_back(pf);
    return index;
}

void DDARSolver::print_equations() const
{
    cout << "Slope Equations:" << endl;
    for (const auto &[eqn, red_eqn] : _equations_slope)
    {
        cout << "Equation: " << eqn << endl;
        cout << "Reduced Equation: " << red_eqn.remainder() << endl;
        cout << endl;
    }
    cout << "Dist Equations:" << endl;
    for (const auto &[eqn, red_eqn] : _equations_dist)
    {
        cout << "Equation: " << eqn << endl;
        cout << "Reduced Equation: " << red_eqn.remainder() << endl;
        cout << endl;
    }
    cout << "DistLog Equations:" << endl;
    for (const auto &[eqn, red_eqn] : _equations_distlog)
    {
        cout << "Equation: " << eqn << endl;
        cout << "Reduced Equation: " << red_eqn.remainder() << endl;
        cout << endl;
    }

    _system_dist.print_equations();

    _system_distlog.print_equations();

    _system_slope.print_equations();
}

bool DDARSolver::establish_statement(Proof *pf, size_t thm_id)
{
    if (pf->is_proved())
    {
        return false;
    }
    pf->set_theorem(thm_id, _level);
    return true;
}

vector<ReducedEquation *> DDARSolver::insert_equation(const unique_ptr<Statement> &pf, string type)
{
    vector<ReducedEquation *> res;

    if (type == "dist")
    {
        auto eqn_ptrs = pf->as_equation_dist(_exp_enabled);
        if (!eqn_ptrs.empty())
        {
            for (const auto &eqn_ptr : eqn_ptrs)
            {
                LinearSystem *sys = &_system_dist;
                eqns_map_type *eqns = &_equations_dist;
                if (!eqn_ptr->empty())
                {
                    Rational coeff = Rational(1) / eqn_ptr->begin()->coeff();
                    Equation eqn = *eqn_ptr * coeff;
                    auto red_eq = ReducedEquation(eqn, sys);
                    res.push_back(&(eqns->insert({eqn, red_eq}).first->second));
                }
            }
        }
        return res;
    }
    if (type == "slope")
    {
        auto eqn_ptrs = pf->as_equation_slope(_exp_enabled);
        if (!eqn_ptrs.empty())
        {
            for (const auto &eqn_ptr : eqn_ptrs)
            {
                LinearSystem *sys = &_system_slope;
                eqns_map_type *eqns = &_equations_slope;
                if (!eqn_ptr->empty())
                {
                    Rational coeff = Rational(1) / eqn_ptr->begin()->coeff();
                    Equation eqn = *eqn_ptr * coeff;
                    auto red_eq = ReducedEquation(eqn, sys);
                    res.push_back(&(eqns->insert({eqn, red_eq}).first->second));
                }
            }
        }
        return res;
    }
    if (type == "distlog" && _log_enabled)
    {
        auto eqn_ptrs = pf->as_equation_distlog(_exp_enabled);
        if (!eqn_ptrs.empty())
        {
            for (const auto &eqn_ptr : eqn_ptrs)
            {
                LinearSystem *sys = &_system_distlog;
                eqns_map_type *eqns = &_equations_distlog;
                if (!eqn_ptr->empty())
                {
                    Rational coeff = Rational(1) / eqn_ptr->begin()->coeff();
                    Equation eqn = *eqn_ptr * coeff;
                    auto red_eq = ReducedEquation(eqn, sys);
                    res.push_back(&(eqns->insert({eqn, red_eq}).first->second));
                }
            }
        }
        return res;
    }

    return res;
}

void DDARSolver::add_established_equations(Proof *pf)
{
    _system_dist.add_reduced_equation(pf, "dist");
    _system_distlog.add_reduced_equation(pf, "distlog");
    _system_slope.add_reduced_equation(pf, "slope");
    if (pf->name() == "eqpoint")
    {
        auto pts = pf->statement()->points();
        Point p = pts[0];
        Point q = pts[1];
        std::vector<Proof *> to_process;
        for (const auto &old_pf : _checked_statements)
        {
            if (old_pf->statement()->contain(p) && !old_pf->statement()->contain(q))
            {
                to_process.push_back(old_pf);
            }
        }
        for (auto &old_pf : to_process)
        {
            auto stmt = old_pf->statement()->replace(p, q);
            string key = stmt->normalize()->to_string();
            auto itr = _statement_proofs.find(key);
            if (itr != _statement_proofs.end())
            {
                Proof *new_pf = itr->second.get();
                if (!new_pf->is_proved())
                {
                    new_pf->set_proved(pf, old_pf);
                }
            }
        }
    }
}
