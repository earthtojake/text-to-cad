# JSON

Portable JSON value types and utilities shared by core primitives.

`JsonValue` permits immutable JSON-shaped values, including object properties
whose `undefined` value is omitted at serialization boundaries. `deepFreeze()`
recursively freezes a validated JSON value and preserves its inferred type.
