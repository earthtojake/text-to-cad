// json.hpp: compact JSON text as Python's json.dumps(separators=(",", ":")) writes it, numbers by float.__repr__
// (the shortest text that reads back as the same double), so the core's answers are byte-comparable to cad's.
#pragma once

#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace vc {

// float.__repr__: shortest round-trip digits; exponent form when the point would fall before -4 or after 16 places.
inline void append_double(std::string& out, double value) {
  if (std::isnan(value)) { out += "NaN"; return; }
  if (std::isinf(value)) { out += value < 0 ? "-Infinity" : "Infinity"; return; }
  if (value == 0) { out += std::signbit(value) ? "-0.0" : "0.0"; return; }
  char buf[64];
  auto res = std::to_chars(buf, buf + sizeof buf, value, std::chars_format::scientific);
  std::string text(buf, res.ptr);
  bool negative = text[0] == '-';
  if (negative) text.erase(0, 1);
  size_t e = text.find('e');
  std::string digits = text.substr(0, e);
  int exponent = std::atoi(text.c_str() + e + 1);
  if (digits.size() > 1) digits.erase(1, 1);  // drop the point
  int decpt = exponent + 1;
  int n = (int)digits.size();
  if (negative) out += '-';
  if (decpt <= -4 || decpt > 16) {
    out += digits[0];
    if (n > 1) { out += '.'; out.append(digits, 1, std::string::npos); }
    char ex[16];
    std::snprintf(ex, sizeof ex, "e%c%02d", exponent < 0 ? '-' : '+', std::abs(exponent));
    out += ex;
  } else if (decpt <= 0) {
    out += "0.";
    out.append(-decpt, '0');
    out += digits;
  } else if (decpt >= n) {
    out += digits;
    out.append(decpt - n, '0');
    out += ".0";
  } else {
    out.append(digits, 0, decpt);
    out += '.';
    out.append(digits, decpt, std::string::npos);
  }
}

// Python's round(value, 6): the correctly rounded decimal, read back.
inline double round6(double value) {
  char buf[512];
  std::snprintf(buf, sizeof buf, "%.6f", value);
  return std::strtod(buf, nullptr);
}

class Json {
 public:
  std::string out;

  Json& open() { comma(); out += '{'; first_.push_back(true); return *this; }
  Json& close() { out += '}'; first_.pop_back(); return *this; }
  Json& open_list() { comma(); out += '['; first_.push_back(true); return *this; }
  Json& close_list() { out += ']'; first_.pop_back(); return *this; }
  Json& key(const std::string& name) { comma(); string_(name); out += ':'; pending_ = true; return *this; }
  Json& key(long long ordinal) { return key(std::to_string(ordinal)); }
  Json& num(double value) { comma(); append_double(out, value); return *this; }
  Json& integer(long long value) { comma(); out += std::to_string(value); return *this; }
  Json& boolean(bool value) { comma(); out += value ? "true" : "false"; return *this; }
  Json& null() { comma(); out += "null"; return *this; }
  Json& str(const std::string& text) { comma(); string_(text); return *this; }
  Json& raw(const std::string& text) { comma(); out += text; return *this; }  // JSON already written (a number)
  Json& point(double x, double y, double z) { open_list().num(x).num(y).num(z); return close_list(); }

 private:
  std::vector<bool> first_;
  bool pending_ = false;  // a key was written: its value takes no comma

  void comma() {
    if (pending_) { pending_ = false; return; }
    if (!first_.empty()) {
      if (!first_.back()) out += ',';
      first_.back() = false;
    }
  }
  void string_(const std::string& text) {
    out += '"';
    for (unsigned char c : text) {
      switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        default:
          if (c < 0x20) {
            char esc[8];
            std::snprintf(esc, sizeof esc, "\\u%04x", c);
            out += esc;
          } else {
            out += (char)c;  // UTF-8 as it is (the ABI's JSON is UTF-8)
          }
      }
    }
    out += '"';
  }
};

}  // namespace vc
