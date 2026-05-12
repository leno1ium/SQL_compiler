from typing import Dict, Callable, Any


class FunctionManager:
    """Менеджер для обработки SQL функций"""

    _functions: Dict[str, Callable] = {}
    _aggregates: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, func: Callable, is_aggregate: bool = False):
        """Зарегистрировать функцию"""
        name = name.upper()
        if is_aggregate:
            cls._aggregates[name] = func
        else:
            cls._functions[name] = func

    @classmethod
    def is_aggregate(cls, name: str) -> bool:
        """Проверить, является ли функция агрегатной"""
        return name.upper() in cls._aggregates

    @classmethod
    def call(cls, name: str, *args, **kwargs) -> Any:
        """Вызвать зарегистрированную функцию"""
        name = name.upper()
        print(f"[DEBUG] FunctionManager.call: {name} with args={args}")
        print(f"[DEBUG] Registered functions: {list(cls._functions.keys())}")

        if name in cls._functions:
            func = cls._functions[name]
            print(f"[DEBUG] Function type: {type(func)}")
            result = func(*args, **kwargs)
            print(f"[DEBUG] Result: {result}")
            return result

        raise ValueError(f"Unknown function: {name}")

    @classmethod
    def call_aggregate(cls, name: str, values: list, distinct: bool = False) -> Any:
        """Вызвать агрегатную функцию"""
        name = name.upper()

        if name in cls._aggregates:
            return cls._aggregates[name](values, distinct)

        raise ValueError(f"Unknown aggregate function: {name}")


# Регистрируем стандартные функции
def _register_standard_functions():
    """Регистрация стандартных SQL функций"""

    # Строковые функции - просто функции
    FunctionManager.register("UPPER", lambda x: x.upper() if isinstance(x, str) else x)
    FunctionManager.register("LOWER", lambda x: x.lower() if isinstance(x, str) else x)
    FunctionManager.register("LENGTH", lambda x: len(str(x)) if x is not None else 0)
    FunctionManager.register("TRIM", lambda x: x.strip() if isinstance(x, str) else x)

    # Агрегатные функции
    def count(values, distinct=False):
        if distinct:
            values = list(set(values))
        return sum(1 for v in values if v is not None)

    def sum_(values, distinct=False):
        if distinct:
            values = list(set(values))
        valid = [v for v in values if isinstance(v, (int, float)) and v is not None]
        return sum(valid) if valid else 0

    def avg(values, distinct=False):
        if distinct:
            values = list(set(values))
        valid = [v for v in values if isinstance(v, (int, float)) and v is not None]
        return sum(valid) / len(valid) if valid else 0

    def min_(values, distinct=False):
        if distinct:
            values = list(set(values))
        valid = [v for v in values if v is not None]
        return min(valid) if valid else None

    def max_(values, distinct=False):
        if distinct:
            values = list(set(values))
        valid = [v for v in values if v is not None]
        return max(valid) if valid else None

    FunctionManager.register("COUNT", count, is_aggregate=True)
    FunctionManager.register("SUM", sum_, is_aggregate=True)
    FunctionManager.register("AVG", avg, is_aggregate=True)
    FunctionManager.register("MIN", min_, is_aggregate=True)
    FunctionManager.register("MAX", max_, is_aggregate=True)

    print("[DEBUG] Functions registered:", list(FunctionManager._functions.keys()))
    print("[DEBUG] Aggregates registered:", list(FunctionManager._aggregates.keys()))


# Вызываем регистрацию при импорте
_register_standard_functions()