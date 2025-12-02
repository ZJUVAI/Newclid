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

using namespace std;

DDARSolver::DDARSolver(Problem *problem, bool log_enabled, bool exp_enabled) : _problem(problem), _log_enabled(log_enabled), _exp_enabled(exp_enabled)
{
    // cout << "添加前提条件" << endl;
    for (const auto &hyp : problem->hypotheses())
    {
        this->insert_statement(hyp->normalize())->prove_by_assumption();
        // cout << hyp->to_string() << "已添加" << endl;
    }

    // cout << "匹配定理" << endl;
    Matcher matcher(problem);
    for (const auto &thm : matcher.theorems())
    {
        insert_application(thm.clone());
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

    // for (const auto &stmt : matcher.stmts())
    // {
    //     _ars.push_back(this->insert_statement(stmt));
    // }
}

bool DDARSolver::run_level(const Point &max_pt)
{
    size_t num_stmts = _checked_statements.size();
    // cout << "开始第" << _level << "层, 初始有" << num_stmts << "个结论" << endl;
    // for (auto const &pf : _checked_statements)
    // {
    //     cout << pf->statement()->to_string() << "已证明" << endl;
    // }

    size_t const n = _applications.size();
    for (size_t i = 0; i < n; i++)
    {
        if (_applications[i].max_point() <= max_pt)
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
                goal->ar();
                if (!goal->is_proved())
                {
                    res = false;
                }
            }
        }
        _solved = res;
    }

    // cout << "新证明" << _checked_statements.size() - num_stmts << "个结论, "
    //      << "总计" << _checked_statements.size() << "个结论" << endl;

    ++_level;
    return num_stmts < _checked_statements.size();
}

bool DDARSolver::run(size_t max_levels)
{
    if (_problem->goals().empty())
    {
        for (Point const &max_pt : _problem->points())
        {
            for (size_t i = 0; i < max_levels; i++)
            {
                if (!run_level(max_pt))
                {
                    break;
                }
            }
        }

        _solved = true;
    }
    else
    {
        auto const max_pt = _problem->points().back();
        for (size_t i = 0; i < max_levels; i++)
        {
            if (!run_level(max_pt))
            {
                // cout << "没有新结论, 提前结束" << endl;
                break;
            }
            if (_solved)
            {
                // cout << "目标已证明, 提前结束" << endl;
                break;
            }
        }
    }

    // _system.print_equations();

    return _solved;
}

void DDARSolver::advance_theorem(size_t index)
{
    auto &app = _applications[index];
    if (app.state() != ApplicationState::PENDING)
    {
        return;
    }

    app.advance_proof();
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

size_t DDARSolver::push_established_statement(const Proof *pf)
{
    size_t const index = _checked_statements.size();
    _checked_statements.push_back(pf);
    return index;
}

void DDARSolver::print_equations() const
{
    cout << "Equations:" << endl;
    for (const auto &[eqn, red_eqn] : _equations)
    {
        cout << "Equation: " << eqn << endl;
        cout << "Reduced Equation: " << red_eqn.remainder() << endl;
        cout << endl;
    }
}

bool DDARSolver::establish_statement(Proof *pf, size_t thm_id)
{
    if (pf->is_proved())
    {
        return false;
    }
    pf->ar();
    if (!pf->is_proved())
    {
        pf->set_theorem(thm_id);
    }
    return true;
}

vector<ReducedEquation *> DDARSolver::insert_equation(const unique_ptr<Statement> &pf)
{
    auto eqn_ptrs = pf->as_equation(_log_enabled, _exp_enabled);
    if (eqn_ptrs.empty())
    {
        return {};
    }

    vector<ReducedEquation *> res;
    for (const auto &eqn_ptr : eqn_ptrs)
    {
        LinearSystem *sys = &_system;
        eqns_map_type *eqns = &_equations;
        if (!eqn_ptr->empty())
        {
            Rational coeff = Rational(1) / eqn_ptr->begin()->coeff();
            Equation eqn = *eqn_ptr * coeff;
            auto red_eq = ReducedEquation(eqn, sys);
            res.push_back(&(eqns->insert({eqn, red_eq}).first->second));
        }
    }
    return res;
}

void DDARSolver::add_established_equations(Proof *pf)
{
    _system.add_reduced_equation(pf);
}