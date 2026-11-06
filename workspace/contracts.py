"""Small strict JSON Schema validator for the delivered schema vocabulary.

Schemas are also consumable by full draft 2020-12 validators. Unsupported
keywords fail closed so a schema cannot silently outgrow this implementation.
"""
from pathlib import Path
import re
from numeric import strict_loads

SCHEMAS = Path(__file__).resolve().parent / "contracts"


def validate(value, schema, path="$"):
    supported = {"$schema", "$id", "title", "description", "type", "properties", "required",
                 "additionalProperties", "items", "minItems", "maxItems", "enum", "const",
                 "minimum", "maximum", "pattern", "anyOf", "maxLength"}
    if set(schema) - supported:
        raise ValueError("unsupported_schema_keyword")
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate(value, option, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: no_matching_schema")
    types = {"object": dict, "array": list, "integer": int, "string": str, "boolean": bool, "null": type(None)}
    if "type" in schema and type(value) is not types[schema["type"]]:
        raise ValueError(f"{path}: invalid_type")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: invalid_constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid_enum")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if set(schema.get("required", [])) - value.keys():
            raise ValueError(f"{path}: missing_field")
        for k, v in value.items():
            if k in props:
                validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{path}.{k}: unknown_field")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(v, schema["additionalProperties"], f"{path}.{k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10**9):
            raise ValueError(f"{path}: invalid_length")
        for i, v in enumerate(value):
            validate(v, schema.get("items", {}), f"{path}[{i}]")
    if type(value) is int:
        if value < schema.get("minimum", -10**100) or value > schema.get("maximum", 10**100):
            raise ValueError(f"{path}: out_of_range")
    if isinstance(value, str):
        if len(value) > schema.get("maxLength", 10**9) or ("pattern" in schema and not re.fullmatch(schema["pattern"], value)):
            raise ValueError(f"{path}: invalid_string")


def validate_named(value, name):
    validate(value, strict_loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")))
