#ifndef OBJECT_TABLE_HPP
#define OBJECT_TABLE_HPP

#include "type/point.hpp"
#include "type/object.hpp"
#include "ar/term_arg.hpp"
#include <map>
#include <unordered_map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

class Proof;

class ObjectTable
{
private:
    std::map<std::string, std::shared_ptr<Object>> _obj_map;
    std::unordered_map<std::shared_ptr<Object>, std::vector<TermArg>> _obj_map_reverse;

    size_t _version{0};

    static std::string make_key(const TermArg &s)
    {
        return s.to_string();
    }

public:
    ObjectTable() = default;

    std::shared_ptr<Object> get_obj(const TermArg &s);

    std::shared_ptr<Object> get_or_create_obj(const TermArg &s);

    void merge(const std::vector<TermArg> &terms, std::vector<Proof *> reason);

    std::vector<std::pair<std::string, Object *>> get_all_objs() const;

    void print() const;

    const std::unordered_map<std::shared_ptr<Object>, std::vector<TermArg>> &obj_map_reverse() const { return _obj_map_reverse; }

    size_t version() const { return _version; }
};

#endif // OBJECT_TABLE_HPP