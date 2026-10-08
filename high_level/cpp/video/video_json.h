#pragma once
// =============================================================================
// Minimal JSON parser (no dependencies).
//
// It exists so the core package can read the robot's camera state answer
// without pulling in a third-party library. Objects, arrays, strings, numbers,
// booleans and null are supported, including \uXXXX escapes.
//
// Usage:
//   json::Value root;
//   std::string error;
//   if (json::parse(body, &root, &error)) { (*root.find("camera1")) ... }
// =============================================================================

#include <cctype>
#include <cstdlib>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace robot {
namespace video {
namespace json {

class Value
{
public:
    enum class Type { Null, Bool, Number, String, Array, Object };

    /// Type of this node.
    Type type() const { return type_; }
    bool is_null() const { return type_ == Type::Null; }
    bool is_bool() const { return type_ == Type::Bool; }
    bool is_number() const { return type_ == Type::Number; }
    bool is_string() const { return type_ == Type::String; }
    bool is_array() const { return type_ == Type::Array; }
    bool is_object() const { return type_ == Type::Object; }

    /// Number of object members / array elements.
    size_t size() const { return children_.size(); }

    /// Element of an array (out of range gives a null value).
    const Value& at(size_t index) const;

    /// Member lookup; nullptr when absent or when this is an array.
    const Value* find(const std::string& key) const;

    /// Members in order (inside an array the key is empty).
    const std::vector<std::pair<std::string, Value>>& children() const { return children_; }

    // -- Convenience getters: a wrong type yields the default --

    const std::string& as_string() const;
    bool as_bool() const { return type_ == Type::Bool ? bool_ : false; }
    double as_number() const { return type_ == Type::Number ? number_ : 0.0; }

private:
    friend class Parser;

    Type type_ = Type::Null;
    bool bool_ = false;
    double number_ = 0.0;
    std::string string_;
    /// Members of an object, or elements of an array (then key is empty).
    std::vector<std::pair<std::string, Value>> children_;
};

/// Parses \p text; on failure returns false and stores the reason in
/// \p error (nothing is thrown).
bool parse(const std::string& text, Value* out, std::string* error);

} // namespace json

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------
namespace json {

namespace {

const Value& null_value()
{
    static const Value value;
    return value;
}

} // namespace  (Parser stays in namespace json to match the friend
                 // declaration inside Value)

class Parser
{
public:
    explicit Parser(const std::string& text)
        : text_(text)
    {
    }

    bool run(Value* out, std::string* error)
    {
        skip_whitespace();
        if (!parse_value(out)) {
            if (error != nullptr) {
                *error = error_.empty() ? "invalid JSON" : error_;
            }
            return false;
        }
        skip_whitespace();
        if (pos_ != text_.size()) {
            if (error != nullptr) {
                *error = "trailing data after the JSON value (at offset "
                            + std::to_string(pos_) + ")";
            }
            return false;
        }
        return true;
    }

private:
    bool parse_value(Value* out)
    {
        if (pos_ >= text_.size()) {
            return fail("unexpected end of input");
        }
        const char c = text_[pos_];
        switch (c) {
        case '{':
            return parse_object(out);
        case '[':
            return parse_array(out);
        case '"':
            out->type_ = Value::Type::String;
            return parse_string(&out->string_);
        case 't':
            return parse_literal("true", out, true);
        case 'f':
            return parse_literal("false", out, false);
        case 'n':
            return parse_null(out);
        default:
            return parse_number(out);
        }
    }

    bool parse_object(Value* out)
    {
        out->type_ = Value::Type::Object;
        ++pos_; // '{'
        skip_whitespace();
        if (pos_ < text_.size() && text_[pos_] == '}') {
            ++pos_;
            return true;
        }
        while (true) {
            skip_whitespace();
            if (pos_ >= text_.size() || text_[pos_] != '"') {
                return fail("object key must be a string");
            }
            std::string key;
            if (!parse_string(&key)) {
                return false;
            }
            skip_whitespace();
            if (pos_ >= text_.size() || text_[pos_] != ':') {
                return fail("missing ':' after an object key");
            }
            ++pos_;
            skip_whitespace();
            Value child;
            if (!parse_value(&child)) {
                return false;
            }
            out->children_.push_back(std::make_pair(key, child));
            skip_whitespace();
            if (pos_ < text_.size() && text_[pos_] == ',') {
                ++pos_;
                continue;
            }
            if (pos_ < text_.size() && text_[pos_] == '}') {
                ++pos_;
                return true;
            }
            return fail("expected ',' or '}' in an object");
        }
    }

    bool parse_array(Value* out)
    {
        out->type_ = Value::Type::Array;
        ++pos_; // '['
        skip_whitespace();
        if (pos_ < text_.size() && text_[pos_] == ']') {
            ++pos_;
            return true;
        }
        while (true) {
            skip_whitespace();
            Value child;
            if (!parse_value(&child)) {
                return false;
            }
            out->children_.push_back(std::make_pair(std::string(), child));
            skip_whitespace();
            if (pos_ < text_.size() && text_[pos_] == ',') {
                ++pos_;
                continue;
            }
            if (pos_ < text_.size() && text_[pos_] == ']') {
                ++pos_;
                return true;
            }
            return fail("expected ',' or ']' in an array");
        }
    }

    bool parse_string(std::string* out)
    {
        ++pos_; // opening quote
        out->clear();
        while (pos_ < text_.size()) {
            const char c = text_[pos_++];
            if (c == '"') {
                return true;
            }
            if (c != '\\') {
                out->push_back(c);
                continue;
            }
            if (pos_ >= text_.size()) {
                return fail("truncated escape sequence");
            }
            const char esc = text_[pos_++];
            switch (esc) {
            case '"':
                out->push_back('"');
                break;
            case '\\':
                out->push_back('\\');
                break;
            case '/':
                out->push_back('/');
                break;
            case 'b':
                out->push_back('\b');
                break;
            case 'f':
                out->push_back('\f');
                break;
            case 'n':
                out->push_back('\n');
                break;
            case 'r':
                out->push_back('\r');
                break;
            case 't':
                out->push_back('\t');
                break;
            case 'u':
                if (!parse_unicode_escape(out)) {
                    return false;
                }
                break;
            default:
                return fail("unknown escape sequence");
            }
        }
        return fail("unterminated string");
    }

    /// \uXXXX -> UTF-8 (surrogate pairs are emitted as-is).
    bool parse_unicode_escape(std::string* out)
    {
        if (pos_ + 4 > text_.size()) {
            return fail("truncated \\u escape");
        }
        unsigned code = 0;
        for (int i = 0; i < 4; ++i) {
            const char c = text_[pos_++];
            code <<= 4;
            if (c >= '0' && c <= '9') {
                code |= static_cast<unsigned>(c - '0');
            } else if (c >= 'a' && c <= 'f') {
                code |= static_cast<unsigned>(c - 'a' + 10);
            } else if (c >= 'A' && c <= 'F') {
                code |= static_cast<unsigned>(c - 'A' + 10);
            } else {
                return fail("bad hex digit in \\u escape");
            }
        }
        if (code < 0x80) {
            out->push_back(static_cast<char>(code));
        } else if (code < 0x800) {
            out->push_back(static_cast<char>(0xC0 | (code >> 6)));
            out->push_back(static_cast<char>(0x80 | (code & 0x3F)));
        } else {
            out->push_back(static_cast<char>(0xE0 | (code >> 12)));
            out->push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
            out->push_back(static_cast<char>(0x80 | (code & 0x3F)));
        }
        return true;
    }

    bool parse_number(Value* out)
    {
        const size_t start = pos_;
        if (pos_ < text_.size() && (text_[pos_] == '-' || text_[pos_] == '+')) {
            ++pos_;
        }
        bool digits = false;
        while (pos_ < text_.size()
            && (std::isdigit(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == '.'
                || text_[pos_] == 'e' || text_[pos_] == 'E' || text_[pos_] == '-'
                || text_[pos_] == '+')) {
            if (std::isdigit(static_cast<unsigned char>(text_[pos_]))) {
                digits = true;
            }
            ++pos_;
        }
        if (!digits) {
            return fail("unexpected character");
        }
        out->type_ = Value::Type::Number;
        out->number_ = std::strtod(text_.substr(start, pos_ - start).c_str(), nullptr);
        return true;
    }

    bool parse_literal(const char* literal, Value* out, bool value)
    {
        const size_t len = std::string(literal).size();
        if (text_.compare(pos_, len, literal) != 0) {
            return fail("invalid literal");
        }
        pos_ += len;
        out->type_ = Value::Type::Bool;
        out->bool_ = value;
        return true;
    }

    bool parse_null(Value* out)
    {
        if (text_.compare(pos_, 4, "null") != 0) {
            return fail("invalid literal");
        }
        pos_ += 4;
        out->type_ = Value::Type::Null;
        return true;
    }

    void skip_whitespace()
    {
        while (pos_ < text_.size()
            && (text_[pos_] == ' ' || text_[pos_] == '\t' || text_[pos_] == '\n'
                || text_[pos_] == '\r')) {
            ++pos_;
        }
    }

    bool fail(const std::string& message)
    {
        error_ = message + " (at offset " + std::to_string(pos_) + ")";
        return false;
    }

    const std::string& text_;
    size_t pos_ = 0;
    std::string error_;
};


inline const Value& Value::at(size_t index) const
{
    if (type_ != Type::Array || index >= children_.size()) {
        return null_value();
    }
    return children_[index].second;
}

inline const Value* Value::find(const std::string& key) const
{
    if (type_ != Type::Object) {
        return nullptr;
    }
    for (size_t i = 0; i < children_.size(); ++i) {
        if (children_[i].first == key) {
            return &children_[i].second;
        }
    }
    return nullptr;
}

inline const std::string& Value::as_string() const
{
    static const std::string empty;
    return type_ == Type::String ? string_ : empty;
}

inline bool parse(const std::string& text, Value* out, std::string* error)
{
    if (out == nullptr) {
        return false;
    }
    Parser parser(text);
    return parser.run(out, error);
}

} // namespace json

} // namespace video
} // namespace robot
