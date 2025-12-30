#include "solver/object_table.hpp"
#include <iostream>

using namespace std;

Object *ObjectTable::get_obj(const TermArg &s)
{
    string key = make_key(s);
    auto it = _obj_map.find(key);
    return (it != _obj_map.end()) ? it->second.get() : nullptr;
}

Object *ObjectTable::get_or_create_obj(const TermArg &s)
{
    string key = make_key(s);
    auto &ptr = _obj_map[key];
    if (!ptr)
    {
        ptr = make_shared<Object>(s.points());
        _obj_map_reverse[ptr].push_back(key);
    }
    return ptr.get();
}

void ObjectTable::merge(const TermArg &s1, const TermArg &s2, vector<Proof *> reason)
{
    // 找到两个Object指针
    string key1 = make_key(s1);
    string key2 = make_key(s2);
    auto it1 = _obj_map.find(key1);
    auto it2 = _obj_map.find(key2);
    if (it1 == _obj_map.end() || it2 == _obj_map.end())
    {
        return;
    }
    shared_ptr<Object> &sp1 = it1->second;
    shared_ptr<Object> &sp2 = it2->second;
    if (sp1 == sp2)
    {
        return;
    }

    // 确定谁替换谁
    shared_ptr<Object> survivor;
    shared_ptr<Object> victim;
    string survivor_key;
    if (key1 > key2)
    {
        survivor = sp1;
        victim = sp2;
        survivor_key = key1;
        _obj_map[key2] = sp1;
    }
    else
    {
        survivor = sp2;
        victim = sp1;
        survivor_key = key2;
        _obj_map[key1] = sp2;
    }

    // 执行Object合并
    survivor->merge(*victim, reason);

    // 更新Object表
    auto &victim_keys = _obj_map_reverse[victim];
    auto &survivor_keys = _obj_map_reverse[survivor];
    for (const string &k : victim_keys)
    {
        survivor_keys.push_back(k);
        _obj_map[k] = survivor;
    }
    _obj_map_reverse.erase(victim);

    // 更新版本号
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
    for (const auto &[obj_ptr, keys] : _obj_map_reverse)
    {
        cout << "Object " << obj_ptr.get() << " represents:";
        for (const string &key : keys)
        {
            cout << " " << key;
        }
        cout << "  | points:";
        for (const auto &p : obj_ptr->points())
        {
            cout << " " << p;
        }
        cout << endl;
    }
}