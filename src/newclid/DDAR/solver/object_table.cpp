#include "solver/object_table.hpp"
#include <iostream>

using namespace std;

shared_ptr<Object> ObjectTable::get_obj(const TermArg &s)
{
    string key = make_key(s);
    auto it = _obj_map.find(key);
    return (it != _obj_map.end()) ? it->second : nullptr;
}

shared_ptr<Object> ObjectTable::get_or_create_obj(const TermArg &s)
{
    string key = make_key(s);
    auto &ptr = _obj_map[key];
    if (!ptr)
    {
        const auto &target_points = s.points();
        for (const auto &[obj_ptr, term_list] : _obj_map_reverse)
        {
            const auto &obj_set = obj_ptr->points_set();
            bool is_subset = std::all_of(
                target_points.begin(), target_points.end(),
                [&obj_set](const Point &p)
                {
                    return obj_set.count(p) > 0;
                });

            if (is_subset)
            {
                ptr = obj_ptr;
                auto &terms = _obj_map_reverse[obj_ptr];
                if (s < *min_element(terms.begin(), terms.end()))
                {
                    _version++;
                }
                terms.push_back(s);
                return obj_ptr;
            }
        }
        ptr = make_shared<Object>(s.points());
        _obj_map_reverse[ptr].push_back(s);
    }
    return ptr;
}

void ObjectTable::merge(const vector<TermArg> &terms, vector<Proof *> reason)
{
    if (terms.size() <= 1)
    {
        return;
    }
    string min_key;
    shared_ptr<Object> survivor;

    // 第一步：找 key 最小的那个作为 survivor
    for (const auto &arg : terms)
    {
        string key = make_key(arg);
        auto it = _obj_map.find(key);
        if (it == _obj_map.end())
        {
            continue;
        }

        if (min_key.empty() || key < min_key)
        {
            min_key = key;
            survivor = it->second;
        }
    }

    if (!survivor)
    {
        return;
    }

    // 第二步：合并所有其他对象到 survivor
    vector<shared_ptr<Object>> victims_merged;

    for (const auto &arg : terms)
    {
        string key = make_key(arg);
        auto it = _obj_map.find(key);
        if (it == _obj_map.end())
        {
            continue;
        }

        shared_ptr<Object> current_obj = it->second;

        if (current_obj == survivor)
        {
            continue;
        }

        survivor->merge(*current_obj, reason);
        auto &survivor_keys = _obj_map_reverse[survivor];
        auto rev_it = _obj_map_reverse.find(current_obj);
        if (rev_it != _obj_map_reverse.end())
        {
            for (const auto &old_arg : rev_it->second)
            {
                string old_key = make_key(old_arg);
                _obj_map[old_key] = survivor;
            }
            survivor_keys.insert(survivor_keys.end(), rev_it->second.begin(), rev_it->second.end());
        }

        victims_merged.push_back(std::move(current_obj));
    }
    for (auto &victim : victims_merged)
    {
        _obj_map_reverse.erase(victim);
    }

    ++_version;
}

vector<pair<string, Object *>> ObjectTable::get_all_objs() const
{
    vector<pair<string, Object *>> result;
    for (const auto &[key, ptr] : _obj_map)
    {
        result.emplace_back(key, ptr.get());
    }
    return result;
}

void ObjectTable::print() const
{
    cout << "ObjectTable (version " << _version << "):" << endl;
    for (const auto &[obj_ptr, args] : _obj_map_reverse)
    {
        cout << "Object " << obj_ptr.get() << " represents:";
        for (const TermArg &arg : args)
        {
            cout << " " << make_key(arg);
        }
        cout << "  | points:";
        for (const auto &p : obj_ptr->points())
        {
            cout << " " << p;
        }
        cout << endl;
    }
}