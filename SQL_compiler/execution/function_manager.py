from typing import Dict, Callable, Any
from datetime import datetime


class FunctionManager:
    _functions: Dict[str, Callable] = {}
    _aggregates: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, func: Callable, is_aggregate: bool = False):
        name = name.upper()
        if is_aggregate:
            cls._aggregates[name] = func
        else:
            cls._functions[name] = func

    @classmethod
    def is_aggregate(cls, name: str) -> bool:
        return name.upper() in cls._aggregates

    @classmethod
    def call(cls, name: str, *args, **kwargs) -> Any:
        name = name.upper()

        if name in cls._aggregates:
            if args:
                if len(args) == 1 and isinstance(args[0], list):
                    return cls._aggregates[name](args[0], False)
                else:
                    return cls._aggregates[name](list(args), False)
            else:
                return None

        if name in cls._functions:
            func = cls._functions[name]
            return func(*args, **kwargs)

        return None

    @classmethod
    def call_aggregate(cls, name: str, values: list, distinct: bool = False) -> Any:
        name = name.upper()

        if name in cls._aggregates:
            return cls._aggregates[name](values, distinct)

        raise ValueError(f"Unknown aggregate function: {name}")


def count(values, distinct=False):
    if distinct:
        unique_values = []
        seen = set()
        for v in values:
            if isinstance(v, (list, dict)):
                v_repr = str(v)
            else:
                v_repr = v
            if v_repr not in seen:
                seen.add(v_repr)
                unique_values.append(v)
        values = unique_values

    if not values:
        return 0

    return sum(1 for v in values if v is not None)


def sum_(values, distinct=False):
    if distinct:
        unique_values = []
        seen = set()
        for v in values:
            if isinstance(v, (list, dict)):
                v_repr = str(v)
            else:
                v_repr = v
            if v_repr not in seen:
                seen.add(v_repr)
                unique_values.append(v)
        values = unique_values

    numeric_values = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            try:
                v = float(v) if '.' in v else int(v)
            except ValueError:
                continue
        if isinstance(v, (int, float)):
            numeric_values.append(v)

    return sum(numeric_values) if numeric_values else 0


def avg(values, distinct=False):
    if distinct:
        unique_values = []
        seen = set()
        for v in values:
            if isinstance(v, (list, dict)):
                v_repr = str(v)
            else:
                v_repr = v
            if v_repr not in seen:
                seen.add(v_repr)
                unique_values.append(v)
        values = unique_values

    numeric_values = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            try:
                v = float(v) if '.' in v else int(v)
            except ValueError:
                continue
        if isinstance(v, (int, float)):
            numeric_values.append(v)

    return sum(numeric_values) / len(numeric_values) if numeric_values else 0


def min_(values, distinct=False):
    if distinct:
        unique_values = []
        seen = set()
        for v in values:
            if isinstance(v, (list, dict)):
                v_repr = str(v)
            else:
                v_repr = v
            if v_repr not in seen:
                seen.add(v_repr)
                unique_values.append(v)
        values = unique_values

    valid = [v for v in values if v is not None]
    return min(valid) if valid else None


def max_(values, distinct=False):
    if distinct:
        unique_values = []
        seen = set()
        for v in values:
            if isinstance(v, (list, dict)):
                v_repr = str(v)
            else:
                v_repr = v
            if v_repr not in seen:
                seen.add(v_repr)
                unique_values.append(v)
        values = unique_values

    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def upper(x):
    return x.upper() if isinstance(x, str) else str(x) if x is not None else None


def lower(x):
    return x.lower() if isinstance(x, str) else str(x) if x is not None else None


def length(x):
    return len(str(x)) if x is not None else 0


def trim(x):
    return x.strip() if isinstance(x, str) else str(x) if x is not None else None


def ltrim(x):
    if isinstance(x, str):
        return x.lstrip()
    return str(x).lstrip() if x is not None else None


def rtrim(x):
    if isinstance(x, str):
        return x.rstrip()
    return str(x).rstrip() if x is not None else None


def substr(x, start, length=None):
    if x is None:
        return None

    s = str(x)
    try:
        start_idx = int(start) - 1
        if length is not None:
            end_idx = start_idx + int(length)
            return s[start_idx:end_idx]
        else:
            return s[start_idx:]
    except (ValueError, IndexError):
        return ''


def concat(*args):
    result = ''
    for arg in args:
        if arg is not None:
            result += str(arg)
    return result


def instr(string, substring):
    if string is None or substring is None:
        return None
    try:
        pos = str(string).find(str(substring))
        return pos + 1 if pos >= 0 else 0
    except:
        return 0


def replace(string, old, new):
    if string is None:
        return None
    try:
        return str(string).replace(str(old), str(new))
    except:
        return str(string)


def to_char(x, format=None):
    if x is None:
        return None
    if isinstance(x, datetime):
        if format:
            fmt_map = {
                'YYYY': '%Y', 'MM': '%m', 'DD': '%d',
                'HH24': '%H', 'MI': '%M', 'SS': '%S'
            }
            for sql_fmt, py_fmt in fmt_map.items():
                if sql_fmt in format.upper():
                    format = format.replace(sql_fmt, py_fmt)
            try:
                return x.strftime(format)
            except:
                return x.strftime('%Y-%m-%d')
        return x.strftime('%Y-%m-%d')
    return str(x)


def to_number(x):
    if x is None:
        return None
    try:
        if isinstance(x, str):
            return float(x) if '.' in x else int(x)
        return float(x)
    except (ValueError, TypeError):
        return 0


def to_date(x, format=None):
    if x is None:
        return None
    if isinstance(x, datetime):
        return x
    if isinstance(x, str):
        formats = [
            '%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d',
            '%d-%m-%Y', '%Y%m%d', '%d.%m.%y'
        ]
        if format:
            fmt_map = {
                'YYYY': '%Y', 'MM': '%m', 'DD': '%d',
                'HH24': '%H', 'MI': '%M', 'SS': '%S'
            }
            for sql_fmt, py_fmt in fmt_map.items():
                if sql_fmt in format.upper():
                    format = format.replace(sql_fmt, py_fmt)
            try:
                return datetime.strptime(x, format)
            except:
                pass
        for fmt in formats:
            try:
                return datetime.strptime(x, fmt)
            except:
                continue
    return None


def round_(x, decimals=0):
    if x is None:
        return None
    try:
        return round(float(x), int(decimals))
    except (ValueError, TypeError):
        return x


def floor_(x):
    if x is None:
        return None
    try:
        import math
        return math.floor(float(x))
    except (ValueError, TypeError):
        return x


def ceil_(x):
    if x is None:
        return None
    try:
        import math
        return math.ceil(float(x))
    except (ValueError, TypeError):
        return x


def mod(x, y):
    if x is None or y is None or y == 0:
        return None
    try:
        return float(x) % float(y)
    except (ValueError, TypeError):
        return None


def power(x, y):
    if x is None or y is None:
        return None
    try:
        return float(x) ** float(y)
    except (ValueError, TypeError):
        return None


def coalesce(*args):
    for arg in args:
        if arg is not None:
            return arg
    return None


def nvl(x, default):
    return default if x is None else x


def nullif(x, y):
    return None if x == y else x


def _register_standard_functions():
    FunctionManager.register("UPPER", upper)
    FunctionManager.register("LOWER", lower)
    FunctionManager.register("LENGTH", length)
    FunctionManager.register("TRIM", trim)
    FunctionManager.register("LTRIM", ltrim)
    FunctionManager.register("RTRIM", rtrim)
    FunctionManager.register("SUBSTR", substr)
    FunctionManager.register("SUBSTRING", substr)
    FunctionManager.register("CONCAT", concat)
    FunctionManager.register("INSTR", instr)
    FunctionManager.register("REPLACE", replace)

    FunctionManager.register("TO_CHAR", to_char)
    FunctionManager.register("TO_NUMBER", to_number)
    FunctionManager.register("TO_DATE", to_date)

    FunctionManager.register("ROUND", round_)
    FunctionManager.register("FLOOR", floor_)
    FunctionManager.register("CEIL", ceil_)
    FunctionManager.register("CEILING", ceil_)
    FunctionManager.register("MOD", mod)
    FunctionManager.register("POWER", power)

    FunctionManager.register("COALESCE", coalesce)
    FunctionManager.register("NVL", nvl)
    FunctionManager.register("NULLIF", nullif)

    FunctionManager.register("COUNT", count, is_aggregate=True)
    FunctionManager.register("SUM", sum_, is_aggregate=True)
    FunctionManager.register("AVG", avg, is_aggregate=True)
    FunctionManager.register("MIN", min_, is_aggregate=True)
    FunctionManager.register("MAX", max_, is_aggregate=True)


_register_standard_functions()