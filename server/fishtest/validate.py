import re
import types

from email_validator import EmailNotValidError, validate_email


class optional_key:
    def __init__(self, key):
        self.key = key


class union:
    def __init__(self, *schemas):
        self.schemas = schemas

    def __validate__(self, object, name, strict=False):
        messages = []
        for schema in self.schemas:
            message = validate(schema, object, name, strict=strict)
            if message == "":
                return ""
            else:
                messages.append(message)
        return " and ".join(messages)


class email:
    @staticmethod
    def __validate__(object, name, strict=False):
        try:
            validate_email(object, check_deliverability=False)
            return ""
        except EmailNotValidError as e:
            return f"{name} is not a valid email address: {str(e)}"


class regex:
    def __init__(self, regex, name=None):
        self.regex = regex
        self.pattern = re.compile(regex)
        self.name = name

    def __validate__(self, object, name, strict=False):
        if self.pattern.fullmatch(object):
            return ""
        else:
            if self.name is None:
                return f"{name} does not match the pattern {self.regex}"
            else:
                return f"{name} is not of type {self.name}"


def _keys(dict):
    ret = set()
    for k in dict:
        if isinstance(k, optional_key):
            ret.add(k.key)
        else:
            ret.add(k)
    return ret


def validate_type(schema, object, name, strict=False):
    assert isinstance(schema, type)
    if not isinstance(object, schema):
        return f"{name} is not of type {schema.__name__}"
    else:
        return ""


def validate_sequence(schema, object, name, strict=False):
    assert isinstance(schema, list) or isinstance(schema, tuple)
    if type(schema) != type(object):
        return f"{name} is not of type {type(schema).__name}"
    l = len(object)
    if strict and l != len(schema):
        return f"{name} does not have length {len(schema)}"
    for i in range(len(schema)):
        name_ = f"{name}[{i}]"
        if i >= l:
            return f"{name_} does not exist"
        else:
            ret = validate(schema[i], object[i], name_, strict=strict)
            if ret != "":
                return ret
    return ""


def validate_dict(schema, object, name, strict=False):
    assert isinstance(schema, dict)
    if type(schema) != type(object):
        return f"{name} is not of type {type(schema).__name}"
    if strict:
        _k = _keys(schema)
        for x in object:
            if x not in _k:
                return f"{name}['{x}'] is not in the schema"
    for k in schema:
        k_ = k
        if isinstance(k, optional_key):
            k_ = k.key
            if k_ not in object:
                continue
        name_ = f"{name}['{k_}']"
        if k_ not in object:
            return f"{name_} is missing"
        else:
            ret = validate(schema[k], object[k_], name_, strict=strict)
            if ret != "":
                return ret
    return ""


def validate_generics(schema, object, name, strict=False):
    assert isinstance(schema, types.GenericAlias)
    root_type = schema.__origin__
    ret = validate_type(root_type, object, name, strict=strict)
    if ret != "":
        return ret
    if root_type not in (tuple, list):
        ret = f"I don't understand the schema {schema}"
        return ret
    args = schema.__args__
    if len(args) == 0:
        ret = f"I don't understand the schema {schema}"
        return ret
    if len(args) == 1:
        arg = args[0]
    else:
        arg = args
    for i in range(len(object)):
        name_ = f"{name}[{i}]"
        ret = validate(arg, object[i], name_, strict=strict)
        if ret != "":
            return ret
    return ""


def validate(schema, object, name, strict=False):
    if hasattr(schema, "__validate__"):  # duck typing
        return schema.__validate__(object, name, strict=strict)
    elif isinstance(schema, types.GenericAlias):
        return validate_generics(schema, object, name, strict=strict)
    elif isinstance(schema, type):
        return validate_type(schema, object, name, strict=strict)
    elif isinstance(schema, list) or isinstance(schema, tuple):
        return validate_sequence(schema, object, name, strict=strict)
    elif isinstance(schema, dict):
        return validate_dict(schema, object, name, strict=strict)
    elif object != schema:
        return f"{name} is not equal to {repr(schema)}"
    return ""
