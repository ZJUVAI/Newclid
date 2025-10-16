#include "predicate/statement.hpp"
#include <memory>
#include <optional>
#include <ostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

ostream &operator<<(ostream &out, const Statement &stmt)
{
    return stmt.print(out);
}

string Statement::to_string() const
{
    string res = name();
    for (const auto &pt : points())
    {
        res += " " + pt.name();
    }
    return res;
}

vector<string> Statement::to_tokens() const
{
    vector<string> tokens = {name()};
    for (const auto &pt : points())
    {
        tokens.push_back(pt.name());
    }
    return tokens;
}