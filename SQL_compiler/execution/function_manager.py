from typing import Dict, Callable, Any, List
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
            return None

        if name in cls._functions:
            try:
                return cls._functions[name](*args, **kwargs)
            except Exception as e:
                print(f"Error calling function {name}: {e}")
                return None

        raise ValueError(f"Unknown function: {name}")

    @classmethod
    def call_aggregate(cls, name: str, values: list, distinct: bool = False) -> Any:
        name = name.upper()
        if name in cls._aggregates:
            return cls._aggregates[name](values, distinct)
        raise ValueError(f"Unknown aggregate function: {name}")


# Агрегатные функции
def count(values: List, distinct: bool = False) -> int:
    if distinct:
        seen = set()
        count_val = 0
        for v in values:
            if v is not None:
                key = str(v) if isinstance(v, (list, dict)) else v
                if key not in seen:
                    seen.add(key)
                    count_val += 1
        return count_val
    return sum(1 for v in values if v is not None)


def sum_(values: List, distinct: bool = False) -> float:
    if distinct:
        seen = set()
        unique_vals = []
        for v in values:
            if v is not None and isinstance(v, (int, float)):
                if v not in seen:
                    seen.add(v)
                    unique_vals.append(v)
        values = unique_vals

    valid = [v for v in values if isinstance(v, (int, float)) and v is not None]
    return sum(valid) if valid else 0


def avg(values: List, distinct: bool = False) -> float:
    if distinct:
        seen = set()
        unique_vals = []
        for v in values:
            if v is not None and isinstance(v, (int, float)):
                if v not in seen:
                    seen.add(v)
                    unique_vals.append(v)
        values = unique_vals

    valid = [v for v in values if isinstance(v, (int, float)) and v is not None]
    if not valid:
        return 0
    return sum(valid) / len(valid)


def min_(values: List, distinct: bool = False) -> Any:
    if distinct:
        seen = set()
        unique_vals = []
        for v in values:
            if v is not None:
                if v not in seen:
                    seen.add(v)
                    unique_vals.append(v)
        values = unique_vals

    valid = [v for v in values if v is not None]
    return min(valid) if valid else None


def max_(values: List, distinct: bool = False) -> Any:
    if distinct:
        seen = set()
        unique_vals = []
        for v in values:
            if v is not None:
                if v not in seen:
                    seen.add(v)
                    unique_vals.append(v)
        values = unique_vals

    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


# Скалярные функции
def to_char(value: Any, format_str: str = None) -> str:
    if value is None:
        return ''

    if isinstance(value, datetime):
        if format_str:

            months_ru = {
                1: 'янв', 2: 'фев', 3: 'мар', 4: 'апр', 5: 'май', 6: 'июн',
                7: 'июл', 8: 'авг', 9: 'сен', 10: 'окт', 11: 'ноя', 12: 'дек'
            }

            if 'Mon' in format_str:
                month_num = value.month
                month_ru = months_ru[month_num]
                format_str = format_str.replace('Mon', month_ru)

            fmt = format_str
            fmt = fmt.replace('DD', '%d')
            fmt = fmt.replace('MM', '%m')
            fmt = fmt.replace('YYYY', '%Y')
            fmt = fmt.replace('YY', '%y')
            return value.strftime(fmt)
        return value.strftime('%Y-%m-%d')

    if isinstance(value, (int, float)):
        if format_str:
            if '999' in format_str:
                return str(int(value))
        return str(value)

    return str(value)

def substr(value: Any, start: int, length: int = None) -> str:
    if value is None:
        return ''

    str_value = str(value)
    # Конвертируем 1-индексацию в 0-индексацию
    start_idx = start - 1 if start > 0 else start

    if start_idx < 0:
        start_idx = 0

    if length is not None and length > 0:
        return str_value[start_idx:start_idx + length]
    return str_value[start_idx:]


def round_func(value: Any, decimals: int = 0) -> float:
    if value is None:
        return 0
    try:
        num = float(value)
        if decimals < 0:
            factor = 10 ** (-decimals)
            return round(num / factor) * factor
        return round(num, decimals)
    except (ValueError, TypeError):
        return 0


def upper_func(value: Any) -> str:
    if value is None:
        return ''
    return str(value).upper()


def lower_func(value: Any) -> str:
    if value is None:
        return ''
    return str(value).lower()


def length_func(value: Any) -> int:
    if value is None:
        return 0
    return len(str(value))


def trim_func(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def init_function_manager():
    """Регистрация всех функций"""
    # Строковые функции
    FunctionManager.register("UPPER", upper_func)
    FunctionManager.register("LOWER", lower_func)
    FunctionManager.register("LENGTH", length_func)
    FunctionManager.register("TRIM", trim_func)
    FunctionManager.register("SUBSTR", substr)
    FunctionManager.register("SUBSTRING", substr)

    # Функции форматирования
    FunctionManager.register("TO_CHAR", to_char)
    FunctionManager.register("ROUND", round_func)

    # Агрегатные функции
    FunctionManager.register("COUNT", count, is_aggregate=True)
    FunctionManager.register("SUM", sum_, is_aggregate=True)
    FunctionManager.register("AVG", avg, is_aggregate=True)
    FunctionManager.register("MIN", min_, is_aggregate=True)
    FunctionManager.register("MAX", max_, is_aggregate=True)


# Регистрируем функции при импорте
init_function_manager()