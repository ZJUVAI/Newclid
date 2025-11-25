#ifndef DDAR_HPP
#define DDAR_HPP

#include <vector>
#include <map>
#include <string>
#include <memory>
#include "problem.hpp"
#include "ar/linear_system.hpp"
#include "ar/reduced_equation.hpp"
#include "typedef.hpp"
#include "theorem.hpp"
#include "solver/application.hpp"
#include "solver/proof.hpp"

class DDARSolver
{
private:
    Problem *_problem;

    size_t _level{0};

    std::vector<Application> _applications;

    std::map<std::string, std::unique_ptr<Proof>> _statement_proofs;

    std::vector<Proof *> _goals;

    std::vector<Proof *> _ars;

    std::vector<const Proof *> _checked_statements;

    bool _solved{false};

    LinearSystem _system;

    using eqns_map_type = std::unordered_map<Equation, ReducedEquation>;

    eqns_map_type _equations;

public:
    bool run_level(const Point &max_pt);

    bool run(size_t max_levels);

    size_t get_level() const { return _level; }

    bool is_solved() const { return _solved; }

    Proof *insert_statement(const std::unique_ptr<Statement> &p);

    const std::vector<Application> &applications() const { return _applications; }

    size_t num_applications() const;

    size_t push_established_statement(const Proof *pf);

    DDARSolver(Problem *problem);

    void advance_theorem(size_t index);

    void insert_application(Theorem thm);

    static bool establish_statement(Proof *pf, size_t thm_id);

    void add_established_equations(Proof *pf);

    void print_equations() const;

    std::vector<std::tuple<std::vector<std::string>, std::vector<std::vector<std::string>>, std::string>> dependency_graph() const;

    std::vector<ReducedEquation *> insert_equation(const std::unique_ptr<Statement> &pf);
};

#endif // DDAR_HPP