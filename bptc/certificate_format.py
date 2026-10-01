"""JSON-shape primitives; no arithmetic semantics or producer dependency."""
def exact(value, expected, path="certificate"):
    if type(value) is not type(expected):
        raise ValueError(f"{path}: wrong type")
    if isinstance(expected, dict):
        if value.keys() != expected.keys():
            raise ValueError(f"{path}: missing or extra fields")
        for key in expected: exact(value[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if len(value) != len(expected): raise ValueError(f"{path}: wrong length")
        for i, (x,y) in enumerate(zip(value,expected)): exact(x,y,f"{path}[{i}]")
    elif value != expected:
        raise ValueError(f"{path}: value mismatch")

def keys(value, fields, path):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f"{path}: expected fields {sorted(fields)}")

def integer(value, path, low=None, high=None):
    if type(value) is not int or (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{path}: invalid integer")

def boolean(value, path):
    if type(value) is not bool: raise ValueError(f"{path}: expected Boolean")

def text(value, path):
    if type(value) is not str or not value: raise ValueError(f"{path}: expected nonempty string")


def strict_json_loads(source):
    """Parse one unambiguous JSON value; reject duplicate keys and non-finite numbers.

    Python's default decoder silently keeps the last duplicate key and accepts
    NaN/Infinity. Neither behavior is part of the serialized evidence contract.
    """
    import json
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"non-finite JSON number: {value}")
    def finite_float(value):
        import math
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"non-finite JSON number: {value}")
        return result
    return json.loads(source, object_pairs_hook=object_pairs,
                      parse_constant=constant, parse_float=finite_float)
