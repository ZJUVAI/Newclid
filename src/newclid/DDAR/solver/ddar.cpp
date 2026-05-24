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
#include <sstream>
#include <iomanip>

using namespace std;

DDARSolver::DDARSolver(Problem *problem, const std::map<std::string, bool> &config)
    : _problem(problem), _config(config)
{
    Matcher matcher(problem, config);

    for (const auto &thm : matcher.theorems())
    {
        insert_application(thm.clone());
    }
    for (const auto &hyp : problem->hypotheses())
    {
        this->insert_statement(hyp->normalize())->prove_by_assumption();
    }
    if (!problem->goals().empty())
    {
        for (const auto &goal : problem->goals())
        {
            _goals.push_back(this->insert_statement(goal->normalize()));
        }
    }
    for (const auto &stmt : matcher.stmts())
    {
        if (stmt->check_numerically())
        {
            _ars.push_back(this->insert_statement(stmt->normalize()));
        }
    }
}

bool DDARSolver::run_level(const Point &max_pt)
{
    size_t num_stmts = _checked_statements.size();
    _level++;

    bool changed = true;
    while (changed)
    {
        changed = false;
        for (auto it = _ars.begin(); it != _ars.end();)
        {
            auto &goal = *it;
            if (goal->max_point() > max_pt)
            {
                ++it;
                continue;
            }
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

    size_t const n = _applications.size();
    for (size_t i = 0; i < n; i++)
    {
        if (_applications[i].max_point() <= max_pt && _applications[i].state() == ApplicationState::PENDING)
        {
            advance_theorem(i);
        }
    }

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

    if (!has_goal)
    {
        for (Point const &pt : _problem->points())
        {
            for (size_t i = 0; i < max_levels; ++i)
            {
                if (!run_level(pt))
                {
                    break;
                }
            }
        }
        _solved = true;
    }
    else
    {
        for (size_t i = 0; i < max_levels; ++i)
        {
            if (!run_level(_problem->points().back()))
            {
                break;
            }
            if (_solved)
            {
                break;
            }
        }
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
    _applications.emplace_back(this, move(thm));
}

void DDARSolver::add_custom_theorems(const vector<CustomRule> &rules)
{
    CustomTheoremMatcher matcher(_problem, rules, _config);

    // cout << "\n=== Matched Custom Theorems ===" << endl;
    size_t idx = 0;
    for (const auto &thm : matcher.theorems())
    {
        if (get_config("verbose", false))
        {
            cout << "[" << idx++ << "] " << thm.name() << " (" << thm.rule() << ")" << endl;

            cout << "  Hypotheses:" << endl;
            for (const auto &hyp : thm.hypotheses())
                cout << "    " << hyp->to_string() << endl;

            cout << "  Conclusions:" << endl;
            for (const auto &con : thm.conclusions())
                cout << "    " << con->to_string() << endl;

            cout << endl;
        }
        insert_application(thm.clone());
    }
    // cout << "Total: " << matcher.theorems().size() << " custom theorems added" << endl;
    // cout << "================================\n" << endl;
}

Proof *DDARSolver::insert_statement(const unique_ptr<Statement> &p)
{
    auto key = p->to_string();
    auto [it, success] = _statement_proofs.insert({key, std::make_unique<Proof>(this, p->clone())});
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
        auto eqn_ptrs = pf->as_equation_dist(get_config("using_exp"));
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
        auto eqn_ptrs = pf->as_equation_slope(get_config("using_exp"));
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
    if (type == "distlog")
    {
        auto eqn_ptrs = pf->as_equation_distlog(get_config("using_exp"));
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
