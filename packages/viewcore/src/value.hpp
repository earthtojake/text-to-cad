// value.hpp: JSON text read into a value and written back as Python's json.loads then json.dumps(separators=(",",
// ":")) would: objects keep their keys' order, an integer stays the integer it was spelled, any other number is a
// double written by float.__repr__. What the core reads this way is text cad's engine stored in the document (a
// material, a part's declarations, the parameters, the animations, the closure), so it is UTF-8 JSON as Python wrote
// it; text that is no JSON is refused by name.
#pragma once

#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "json.hpp"

namespace vc {

struct Value {
  enum Kind { NUL, BOOL, INT, REAL, STRING, LIST, OBJECT } kind = NUL;
  bool flag = false;
  std::string text;  // a string's text, or an integer's digits as spelled
  double real = 0;
  std::vector<Value> items;                        // a list
  std::vector<std::pair<std::string, Value>> keys;  // an object, in order

  static Value parse(const std::string& source);

  const Value* get(const std::string& name) const {
    for (const auto& [key, value] : keys)
      if (key == name) return &value;
    return nullptr;
  }
  bool is_number() const { return kind == INT || kind == REAL; }
  double number() const { return kind == INT ? std::strtod(text.c_str(), nullptr) : real; }

  // Python's ==: ints and floats compare by value, dicts whatever their order.
  bool operator==(const Value& other) const {
    if (is_number() && other.is_number()) return number() == other.number();
    if (kind != other.kind) return false;
    switch (kind) {
      case NUL: return true;
      case BOOL: return flag == other.flag;
      case STRING: return text == other.text;
      case LIST: return items == other.items;
      case OBJECT: {
        if (keys.size() != other.keys.size()) return false;
        for (const auto& [key, value] : keys) {
          const Value* found = other.get(key);
          if (!found || !(*found == value)) return false;
        }
        return true;
      }
      default: return false;
    }
  }
  bool operator!=(const Value& other) const { return !(*this == other); }

  void write(Json& out) const {
    switch (kind) {
      case NUL: out.null(); break;
      case BOOL: out.boolean(flag); break;
      case INT: out.raw(text); break;
      case REAL: out.num(real); break;
      case STRING: out.str(text); break;
      case LIST:
        out.open_list();
        for (const Value& item : items) item.write(out);
        out.close_list();
        break;
      case OBJECT:
        out.open();
        for (const auto& [key, value] : keys) {
          out.key(key);
          value.write(out);
        }
        out.close();
        break;
    }
  }
};

namespace detail {

class Parser {
 public:
  explicit Parser(const std::string& s) : s_(s) {}

  Value document() {
    Value found = value();
    space();
    if (at_ != s_.size()) fail("text after the value");
    return found;
  }

 private:
  const std::string& s_;
  size_t at_ = 0;
  int depth_ = 0;

  [[noreturn]] void fail(const char* why) {
    throw std::runtime_error(std::string("the document holds JSON it cannot read (") + why + " at " +
                             std::to_string(at_) + ")");
  }
  void space() {
    while (at_ < s_.size() && (s_[at_] == ' ' || s_[at_] == '\t' || s_[at_] == '\n' || s_[at_] == '\r')) ++at_;
  }
  bool word(const char* w) {
    size_t n = std::char_traits<char>::length(w);
    if (s_.compare(at_, n, w) != 0) return false;
    at_ += n;
    return true;
  }
  static void utf8(std::string& out, unsigned c) {
    if (c < 0x80) {
      out += (char)c;
    } else if (c < 0x800) {
      out += (char)(0xC0 | (c >> 6));
      out += (char)(0x80 | (c & 63));
    } else if (c < 0x10000) {
      out += (char)(0xE0 | (c >> 12));
      out += (char)(0x80 | ((c >> 6) & 63));
      out += (char)(0x80 | (c & 63));
    } else {
      out += (char)(0xF0 | (c >> 18));
      out += (char)(0x80 | ((c >> 12) & 63));
      out += (char)(0x80 | ((c >> 6) & 63));
      out += (char)(0x80 | (c & 63));
    }
  }
  unsigned hex4() {
    if (at_ + 4 > s_.size()) fail("a short \\u escape");
    unsigned c = (unsigned)std::strtoul(s_.substr(at_, 4).c_str(), nullptr, 16);
    at_ += 4;
    return c;
  }
  std::string string() {
    if (s_[at_] != '"') fail("no string");
    ++at_;
    std::string out;
    while (true) {
      if (at_ >= s_.size()) fail("an open string");
      char c = s_[at_++];
      if (c == '"') return out;
      if (c != '\\') { out += c; continue; }
      if (at_ >= s_.size()) fail("an open escape");
      char e = s_[at_++];
      switch (e) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
          unsigned c1 = hex4();
          if (c1 >= 0xD800 && c1 < 0xDC00 && s_.compare(at_, 2, "\\u") == 0) {
            size_t back = at_;
            at_ += 2;
            unsigned c2 = hex4();
            if (c2 >= 0xDC00 && c2 < 0xE000) {
              c1 = 0x10000 + ((c1 - 0xD800) << 10) + (c2 - 0xDC00);
            } else {
              at_ = back;
            }
          }
          utf8(out, c1);
          break;
        }
        default: fail("an unknown escape");
      }
    }
  }
  Value value() {
    space();
    if (at_ >= s_.size()) fail("no value");
    if (++depth_ > 200) fail("nesting too deep");
    Value v;
    char c = s_[at_];
    if (c == '{') {
      v.kind = Value::OBJECT;
      ++at_;
      space();
      if (at_ < s_.size() && s_[at_] == '}') { ++at_; --depth_; return v; }
      while (true) {
        space();
        std::string key = string();
        space();
        if (at_ >= s_.size() || s_[at_] != ':') fail("no ':'");
        ++at_;
        Value item = value();
        // json.loads keeps a repeated key's last value, at its first place.
        bool replaced = false;
        for (auto& [held, value] : v.keys)
          if (held == key) { value = std::move(item); replaced = true; break; }
        if (!replaced) v.keys.emplace_back(std::move(key), std::move(item));
        space();
        if (at_ < s_.size() && s_[at_] == ',') { ++at_; continue; }
        if (at_ < s_.size() && s_[at_] == '}') { ++at_; break; }
        fail("no ',' or '}'");
      }
    } else if (c == '[') {
      v.kind = Value::LIST;
      ++at_;
      space();
      if (at_ < s_.size() && s_[at_] == ']') { ++at_; --depth_; return v; }
      while (true) {
        v.items.push_back(value());
        space();
        if (at_ < s_.size() && s_[at_] == ',') { ++at_; continue; }
        if (at_ < s_.size() && s_[at_] == ']') { ++at_; break; }
        fail("no ',' or ']'");
      }
    } else if (c == '"') {
      v.kind = Value::STRING;
      v.text = string();
    } else if (word("true")) {
      v.kind = Value::BOOL;
      v.flag = true;
    } else if (word("false")) {
      v.kind = Value::BOOL;
    } else if (word("null")) {
      v.kind = Value::NUL;
    } else if (word("NaN") || word("Infinity") || word("-Infinity")) {
      fail("a number JSON has no spelling for");
    } else {
      size_t start = at_;
      if (s_[at_] == '-') ++at_;
      bool integer = true;
      while (at_ < s_.size()) {
        char d = s_[at_];
        if (d >= '0' && d <= '9') { ++at_; continue; }
        if (d == '.' || d == 'e' || d == 'E' || d == '+' || d == '-') { integer = false; ++at_; continue; }
        break;
      }
      std::string digits = s_.substr(start, at_ - start);
      if (digits.empty() || digits == "-") fail("no value");
      if (integer) {
        v.kind = Value::INT;
        // int(text) written back: no "-0", no leading zeros.
        bool negative = digits[0] == '-';
        size_t first = negative ? 1 : 0;
        while (first + 1 < digits.size() && digits[first] == '0') ++first;
        v.text = digits.substr(first);
        if (negative && v.text != "0") v.text = "-" + v.text;
      } else {
        v.kind = Value::REAL;
        char* end = nullptr;
        v.real = std::strtod(digits.c_str(), &end);
        if (end != digits.c_str() + digits.size()) fail("a malformed number");
      }
    }
    --depth_;
    return v;
  }
};

}  // namespace detail

inline Value Value::parse(const std::string& source) { return detail::Parser(source).document(); }

}  // namespace vc
