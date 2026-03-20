#include "rule_parser.hpp"
#include <sstream>
#include <algorithm>
#include <stdexcept>
#include <iostream>

using namespace std;

string RuleParser::trim(const string& str)
{
    size_t first = str.find_first_not_of(" \t\n\r");
    if (first == string::npos)
        return "";
    size_t last = str.find_last_not_of(" \t\n\r");
    return str.substr(first, last - first + 1);
}

pair<vector<string>, vector<string>> RuleParser::split_rule(const string& rule_text)
{
    // Find the "=>" separator
    size_t arrow_pos = rule_text.find("=>");
    if (arrow_pos == string::npos)
    {
        throw runtime_error("Invalid rule format: missing '=>' separator in rule: " + rule_text);
    }

    string premises_str = rule_text.substr(0, arrow_pos);
    string conclusions_str = rule_text.substr(arrow_pos + 2);

    vector<string> premises;
    vector<string> conclusions;

    // Split premises by comma
    stringstream ss_premises(premises_str);
    string clause;
    while (getline(ss_premises, clause, ','))
    {
        clause = trim(clause);
        if (!clause.empty())
        {
            premises.push_back(clause);
        }
    }

    // Split conclusions by comma
    stringstream ss_conclusions(conclusions_str);
    while (getline(ss_conclusions, clause, ','))
    {
        clause = trim(clause);
        if (!clause.empty())
        {
            conclusions.push_back(clause);
        }
    }

    if (premises.empty())
    {
        throw runtime_error("Invalid rule format: no premises found in rule: " + rule_text);
    }

    if (conclusions.empty())
    {
        throw runtime_error("Invalid rule format: no conclusions found in rule: " + rule_text);
    }

    return make_pair(premises, conclusions);
}

pair<string, vector<string>> RuleParser::parse_clause(const string& clause)
{
    stringstream ss(clause);
    string predicate;
    ss >> predicate;

    vector<string> args;
    string arg;
    while (ss >> arg)
    {
        args.push_back(arg);
    }

    if (predicate.empty())
    {
        throw runtime_error("Invalid clause format: empty predicate in clause: " + clause);
    }

    return make_pair(predicate, args);
}

Theorem RuleParser::parse_rule(
    const string& rule_text,
    const string& rule_id,
    Problem* problem)
{
    try
    {
        // Split into premises and conclusions
        auto [premise_strs, conclusion_strs] = split_rule(rule_text);

        // Create theorem
        Theorem thm(rule_id, rule_text);

        // Parse and add premises
        for (const auto& premise_str : premise_strs)
        {
            auto [predicate, args] = parse_clause(premise_str);
            auto stmt = problem->create_statement(predicate, args);
            thm.add_hypothesis(move(stmt));
        }

        // Parse and add conclusions
        for (const auto& conclusion_str : conclusion_strs)
        {
            auto [predicate, args] = parse_clause(conclusion_str);
            auto stmt = problem->create_statement(predicate, args);
            thm.add_conclusion(move(stmt));
        }

        return thm;
    }
    catch (const exception& e)
    {
        throw runtime_error("Failed to parse rule '" + rule_id + "': " + string(e.what()));
    }
}

vector<Theorem> RuleParser::parse_rules(
    const vector<string>& rules_text,
    Problem* problem)
{
    vector<Theorem> theorems;
    theorems.reserve(rules_text.size());

    for (size_t i = 0; i < rules_text.size(); ++i)
    {
        string rule_id = "custom_r" + to_string(i);
        try
        {
            theorems.push_back(parse_rule(rules_text[i], rule_id, problem));
        }
        catch (const exception& e)
        {
            cerr << "Warning: Skipping invalid rule " << i << ": " << e.what() << endl;
            // Continue parsing other rules
        }
    }

    return theorems;
}
