#include "custom_rule_matcher.hpp"
#include <algorithm>
#include <iostream>

using namespace std;

CustomRuleMatcher::CustomRuleMatcher(Problem* problem) : _problem(problem)
{
}

set<string> CustomRuleMatcher::extract_variables(const Theorem& rule)
{
    set<string> variables;

    // Extract from hypotheses
    for (const auto& hyp : rule.hypotheses())
    {
        for (const auto& pt : hyp->points())
        {
            variables.insert(pt.name());
        }
    }

    // Extract from conclusions
    for (const auto& concl : rule.conclusions())
    {
        for (const auto& pt : concl->points())
        {
            variables.insert(pt.name());
        }
    }

    return variables;
}

void CustomRuleMatcher::generate_bindings(
    const vector<string>& variables,
    const vector<Point>& points,
    map<string, Point>& current_binding,
    size_t index,
    vector<map<string, Point>>& result)
{
    // Base case: all variables bound
    if (index == variables.size())
    {
        result.push_back(current_binding);
        return;
    }

    const string& var = variables[index];

    // Try binding this variable to each available point
    for (const auto& pt : points)
    {
        // Check if this point is already used
        bool already_used = false;
        for (const auto& [bound_var, bound_pt] : current_binding)
        {
            if (bound_pt.name() == pt.name())
            {
                already_used = true;
                break;
            }
        }

        if (!already_used)
        {
            current_binding.insert({var, pt});
            generate_bindings(variables, points, current_binding, index + 1, result);
            current_binding.erase(var);
        }
    }
}

vector<map<string, Point>> CustomRuleMatcher::find_bindings(const Theorem& rule)
{
    // Extract variables from rule
    set<string> var_set = extract_variables(rule);
    vector<string> variables(var_set.begin(), var_set.end());

    // Limit to prevent combinatorial explosion
    const size_t MAX_VARIABLES = 8;
    if (variables.size() > MAX_VARIABLES)
    {
        cerr << "Warning: Rule has " << variables.size()
             << " variables (max " << MAX_VARIABLES << "), skipping" << endl;
        return {};
    }

    // Get available points
    vector<Point> points = _problem->points();

    // Generate all possible bindings
    vector<map<string, Point>> all_bindings;
    map<string, Point> current_binding;
    generate_bindings(variables, points, current_binding, 0, all_bindings);

    // Filter by numerical validation
    vector<map<string, Point>> valid_bindings;
    for (const auto& binding : all_bindings)
    {
        if (validate_binding(rule, binding))
        {
            valid_bindings.push_back(binding);
        }
    }

    return valid_bindings;
}

bool CustomRuleMatcher::validate_binding(
    const Theorem& rule,
    const map<string, Point>& binding)
{
    // Instantiate hypotheses with this binding
    vector<unique_ptr<Statement>> instantiated_hyps;
    for (const auto& hyp : rule.hypotheses())
    {
        instantiated_hyps.push_back(instantiate_statement(hyp, binding));
    }

    // Check all hypotheses numerically
    for (const auto& hyp : instantiated_hyps)
    {
        if (!hyp->check_numerically())
        {
            return false;
        }
    }

    return true;
}

unique_ptr<Statement> CustomRuleMatcher::instantiate_statement(
    const unique_ptr<Statement>& stmt,
    const map<string, Point>& binding)
{
    // Get the statement's points
    vector<Point> old_points = stmt->points();
    vector<string> point_names;

    for (const auto& pt : old_points)
    {
        auto it = binding.find(pt.name());
        if (it != binding.end())
        {
            point_names.push_back(it->second.name());
        }
        else
        {
            // This shouldn't happen if binding is complete
            throw runtime_error("Incomplete binding: missing variable " + pt.name());
        }
    }

    // Create new statement with bound points
    return _problem->create_statement(stmt->name(), point_names);
}

Theorem CustomRuleMatcher::instantiate_rule(
    const Theorem& rule,
    const map<string, Point>& binding)
{
    Theorem instantiated(rule.name(), rule.rule());

    // Instantiate hypotheses
    for (const auto& hyp : rule.hypotheses())
    {
        instantiated.add_hypothesis(instantiate_statement(hyp, binding));
    }

    // Instantiate conclusions
    for (const auto& concl : rule.conclusions())
    {
        instantiated.add_conclusion(instantiate_statement(concl, binding));
    }

    return instantiated;
}

vector<Theorem> CustomRuleMatcher::match_rules(const vector<Theorem>& rules)
{
    vector<Theorem> matched_theorems;

    for (const auto& rule : rules)
    {
        // Find all valid bindings for this rule
        auto bindings = find_bindings(rule);

        // Instantiate the rule for each valid binding
        for (const auto& binding : bindings)
        {
            try
            {
                Theorem instantiated = instantiate_rule(rule, binding);

                // Verify the instantiated theorem is numerically valid
                if (instantiated.check_numerically())
                {
                    matched_theorems.push_back(move(instantiated));
                }
            }
            catch (const exception& e)
            {
                cerr << "Warning: Failed to instantiate rule " << rule.name()
                     << ": " << e.what() << endl;
            }
        }
    }

    return matched_theorems;
}
