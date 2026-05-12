from typing import Dict, Any, Optional, List

from SQL_compiler.execution.table import Table
from SQL_compiler.parsing.ast_nodes import *


class RowContext:
    def __init__(self, table: Table, row: Dict[str, Any], tables: Dict[str, Table] = None):
        self.table = table
        self.row = row
        self.row_index = -1
        self.tables = tables or {}  # Добавляем tables

    def get_value(self, column_name: str) -> Any:
        # Прямое совпадение
        if column_name in self.row:
            return self.row[column_name]

        # Составное имя (таблица.колонка)
        if "." in column_name and column_name in self.row:
            return self.row[column_name]

        # Поиск по имени без префикса
        base_name = column_name.split(".")[-1]

        # Точное совпадение base_name
        if base_name in self.row:
            return self.row[base_name]

        # Поиск среди ключей, заканчивающихся на .base_name
        matches = [self.row[key] for key in self.row.keys()
                   if key.endswith(f".{base_name}")]

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise Exception(f'Column "{column_name}" is ambiguous')

        raise KeyError(f"Column '{column_name}' not found in row with keys: {list(self.row.keys())}")

    def get_type(self, column_name: str) -> type:
        return self.table.get_column_type(column_name)

    def has_column(self, column_name: str) -> bool:
        if column_name in self.row:
            return True
        if "." in column_name and column_name in self.row:
            return True
        base_name = column_name.split(".")[-1]
        if base_name in self.row:
            return True
        return any(key.endswith(f".{base_name}") for key in self.row.keys())


class GroupContext:
    def __init__(self, rows: List[Dict[str, Any]]):
        self.rows = rows

    def get_value(self, column_name: str) -> Any:
        """Получить значение из группы (для неагрегированных колонок в HAVING)"""
        if not self.rows:
            return None
        # Для GROUP BY колонок берем значение из первой строки
        return self._lookup_value(self.rows[0], column_name)

    def _lookup_value(self, row: Dict[str, Any], column: str) -> Any:
        if not isinstance(column, str):
            if hasattr(column, 'name'):
                column = column.name
            elif hasattr(column, 'full_name'):
                column = column.full_name
            else:
                column = str(column)
        print(f"[DEBUG LOOKUP] Looking for '{column}' in row with keys: {list(row.keys())}")
        if column in row:
            print(f"[DEBUG LOOKUP] Found exact match: {row[column]}")
            return row[column]
        if "." in column and column in row:
            print(f"[DEBUG LOOKUP] Found dotted match: {row[column]}")
            return row[column]
        base_name = column.split(".")[-1]
        if base_name in row:
            print(f"[DEBUG LOOKUP] Found base_name match '{base_name}': {row[base_name]}")
            return row[base_name]
        matches = [(key, val) for key, val in row.items() if key.endswith(f".{base_name}")]
        if len(matches) == 1:
            print(f"[DEBUG LOOKUP] Found suffix match: {matches[0][1]}")
            return matches[0][1]
        elif len(matches) > 1:
            print(f"[DEBUG LOOKUP] Ambiguous: {matches}")
        print(f"[DEBUG LOOKUP] Not found, returning None")
        return None

    def get_aggregate(self, func_name: str, column: Optional[str] = None, distinct: bool = False) -> Any:
        """Вычисление агрегатной функции для группы"""
        print(f"[DEBUG AGG] RAW column: {column} (type: {type(column)})")
        if column is not None and not isinstance(column, str):
            print(f"[DEBUG AGG] Converting column from {type(column)} to str")
            if hasattr(column, 'name'):
                column = column.name
                print(f"[DEBUG AGG] Used column.name: '{column}'")
            elif hasattr(column, 'full_name'):
                column = column.full_name
                print(f"[DEBUG AGG] Used column.full_name: '{column}'")
            else:
                column = str(column)
                print(f"[DEBUG AGG] Used str(column): '{column}'")

        print(f"[DEBUG AGG] Getting aggregate: {func_name}({column}) for group of size {len(self.rows)}")
        func_name = func_name.upper()

        print(f"[DEBUG AGG] Getting aggregate: {func_name}({column}) for group of size {len(self.rows)}")

        if column is not None and not isinstance(column, str):
            if hasattr(column, 'name'):
                column = column.name
            elif hasattr(column, 'full_name'):
                column = column.full_name
            else:
                column = str(column)
        if func_name == "COUNT":
            if column is None:  # COUNT(*)
                result = len(self.rows)
                print(f"[DEBUG AGG] COUNT(*) = {result}")
                return result

            # COUNT(column) - считаем не-NULL значения
            count = 0
            for row in self.rows:
                val = self._lookup_value(row, column)
                print(f"[DEBUG AGG] Row value for {column}: {val}")
                if val is not None:
                    count += 1
            print(f"[DEBUG AGG] COUNT({column}) = {count}")
            return count

        # Для других агрегатных функций
        values = []
        for row in self.rows:
            val = self._lookup_value(row, column) if column else None
            print(f"[DEBUG AGG] Row value for {column}: {val}")
            if val is not None:
                values.append(val)

        print(f"[DEBUG AGG] Values for {func_name}({column}): {values}")

        if not values:
            if func_name in ("SUM", "AVG"):
                return 0
            return None

        if func_name == "SUM":
            result = sum(values)
        elif func_name == "AVG":
            result = sum(values) / len(values)
        elif func_name == "MIN":
            result = min(values)
        elif func_name == "MAX":
            result = max(values)
        else:
            result = None

        print(f"[DEBUG AGG] Result = {result}")
        return result


class ExpressionEvaluator:
    _subquery_cache = {}
    _cache_enabled = True

    def __init__(self, row_context: Optional[RowContext] = None, group_context: Optional[GroupContext] = None):
        self.row_context = row_context
        self.group_context = group_context

    def evaluate(self, node: AstNode) -> Any:
        """Основной метод оценки выражения"""
        if isinstance(node, NumNode):
            return node.num
        elif isinstance(node, StringNode):
            return node.value
        elif isinstance(node, BoolNode):
            return node.value
        elif isinstance(node, NullNode):
            return None
        elif isinstance(node, IdentNode):
            return self._get_column_value(node.name)
        elif isinstance(node, CompoundIdentNode):
            return self._get_column_value(node.full_name)
        elif isinstance(node, BinOpNode):
            return self._evaluate_binop(node)
        elif isinstance(node, UnOpNode):
            return self._evaluate_unop(node)
        elif isinstance(node, BetweenNode):
            return self._evaluate_between(node)
        elif isinstance(node, InNode):
            return self._evaluate_in(node)
        elif isinstance(node, InSubqueryNode):
            return self._evaluate_in_subquery(node)
        elif isinstance(node, IsNullNode):
            return self._evaluate_is_null(node)
        elif isinstance(node, FuncCallNode):
            return self._evaluate_function(node)
        elif isinstance(node, StarNode):
            raise ValueError("StarNode can only be used in SELECT list")
        else:
            raise ValueError(f"Unknown node type: {type(node)}")

    def _get_column_value(self, column_name: str) -> Any:
        """Получить значение колонки"""
        if self.row_context:
            return self.row_context.get_value(column_name)
        elif self.group_context:
            # В HAVING нужно различать агрегатные и GROUP BY колонки
            # Сначала проверяем, не агрегатная ли это функция
            # Для простоты - берем значение из первой строки группы
            if self.group_context.rows:
                return self.group_context._lookup_value(self.group_context.rows[0], column_name)
            return None
        else:
            raise ValueError(f"No context available for column {column_name}")

    def _get_cache_key(self, subquery: SelectStmtNode, context_tables: Dict[str, Table]) -> str:
        """Создать ключ кэша для подзапроса"""
        # Используем строковое представление запроса и список таблиц
        tables_key = tuple(sorted(context_tables.keys()))
        return f"{str(subquery)}|{tables_key}"

    def _evaluate_in_subquery(self, node: InSubqueryNode) -> bool:
        """Обработка IN с подзапросом с кэшированием"""
        left_value = self.evaluate(node.expr)

        tables = {}
        if self.row_context and hasattr(self.row_context, 'tables'):
            tables = self.row_context.tables

        # Создаем ключ кэша
        cache_key = self._get_cache_key(node.subquery, tables)

        # Проверяем кэш
        if cache_key in self._subquery_cache:
            right_values = self._subquery_cache[cache_key]
        else:
            # Выполняем подзапрос только один раз
            from SQL_compiler.execution.executor import QueryExecutor
            executor = QueryExecutor(tables)

            try:
                subquery_rows = executor.execute(node.subquery)
                # Извлекаем значения
                right_values = []
                for row in subquery_rows:
                    if row:
                        value = list(row.values())[0] if row else None
                        if value is not None:
                            right_values.append(value)
                # Сохраняем в кэш
                if self._cache_enabled:
                    self._subquery_cache[cache_key] = right_values
            except Exception as e:
                print(f"Error executing subquery: {e}")
                right_values = []

        right_set = set(right_values)  # O(n) один раз
        result = left_value in right_set  # O(1)

        return not result if node.negated else result

    def _evaluate_in(self, node: InNode) -> bool:
        """Обработка IN со статическим списком"""
        left_value = self.evaluate(node.expr)
        right_values = [self.evaluate(elem) for elem in node.elements]
        result = left_value in right_values
        return not result if node.negated else result

    def _evaluate_between(self, node: BetweenNode) -> bool:
        """Обработка BETWEEN"""
        value = self.evaluate(node.expr)
        low = self.evaluate(node.low)
        high = self.evaluate(node.high)

        if value is None or low is None or high is None:
            result = False
        else:
            result = low <= value <= high

        return not result if node.negated else result

    def _evaluate_is_null(self, node: IsNullNode) -> bool:
        """Обработка IS NULL / IS NOT NULL"""
        value = self.evaluate(node.expr)
        result = value is None
        return not result if node.negated else result

    def _evaluate_binop(self, node: BinOpNode) -> Any:
        """Обработка бинарных операций"""
        left = self.evaluate(node.arg1)
        right = self.evaluate(node.arg2)

        # Обработка NULL
        if left is None or right is None:
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE,
                           BinOp.LIKE, BinOp.NOT_LIKE):
                return False
            return None

        if node.op == BinOp.ADD:
            return left + right
        elif node.op == BinOp.SUB:
            return left - right
        elif node.op == BinOp.MUL:
            return left * right
        elif node.op == BinOp.DIV:
            return left / right if right != 0 else float('inf')
        elif node.op == BinOp.REM:
            return left % right
        elif node.op == BinOp.GT:
            return left > right
        elif node.op == BinOp.GE:
            return left >= right
        elif node.op == BinOp.LT:
            return left < right
        elif node.op == BinOp.LE:
            return left <= right
        elif node.op == BinOp.EQ:
            return left == right
        elif node.op == BinOp.NE or node.op == BinOp.NE2:
            return left != right
        elif node.op == BinOp.AND:
            return left and right
        elif node.op == BinOp.OR:
            return left or right
        elif node.op == BinOp.LIKE:
            return self._evaluate_like(left, right)
        elif node.op == BinOp.NOT_LIKE:
            return not self._evaluate_like(left, right)
        else:
            raise ValueError(f"Unknown operator: {node.op}")

    def _evaluate_like(self, value: str, pattern: str) -> bool:
        """Реализация LIKE"""
        if not isinstance(value, str) or not isinstance(pattern, str):
            return False

        import re
        regex_pattern = re.escape(pattern).replace('%', '.*').replace('_', '.')
        return re.match(f"^{regex_pattern}$", value, re.IGNORECASE) is not None

    def _evaluate_unop(self, node: UnOpNode) -> Any:
        """Обработка унарных операций"""
        arg = self.evaluate(node.arg)

        if node.op == UnOp.NOT:
            return not arg
        elif node.op == UnOp.PLUS:
            return +arg
        elif node.op == UnOp.MINUS:
            return -arg
        else:
            raise ValueError(f"Unknown unary operator: {node.op}")

    def _make_hashable(self, value: Any) -> Any:
        """Преобразовать значение в хешируемый тип"""
        if value is None:
            return None
        if isinstance(value, (int, float, str, bool)):
            return value
        if isinstance(value, list):
            return tuple(self._make_hashable(v) for v in value)
        if isinstance(value, dict):
            return tuple(sorted((k, self._make_hashable(v)) for k, v in value.items()))
        return str(value)

    def _evaluate_function(self, node: FuncCallNode) -> Any:
        """Обработка функций"""
        if self.group_context:
            # Для агрегатных функций в GROUP BY и HAVING
            if node.name == 'COUNT':
                if not node.args or (len(node.args) == 1 and isinstance(node.args[0], StarNode)):
                    return len(self.group_context.rows)
                else:
                    column = self._get_column_from_expr(node.args[0])
                    print(f"[DEBUG] COUNT column from _get_column_from_expr: {column} (type: {type(column)})")
                    return self.group_context.get_aggregate('COUNT', column)
            elif node.name == 'SUM':
                column = self._get_column_from_expr(node.args[0])
                return self.group_context.get_aggregate('SUM', column)
            elif node.name == 'AVG':
                column = self._get_column_from_expr(node.args[0])
                return self.group_context.get_aggregate('AVG', column)
            elif node.name == 'MIN':
                column = self._get_column_from_expr(node.args[0])
                return self.group_context.get_aggregate('MIN', column)
            elif node.name == 'MAX':
                column = self._get_column_from_expr(node.args[0])
                return self.group_context.get_aggregate('MAX', column)
            else:
                return None
        else:
            # Скалярные функции
            if node.name == 'UPPER' and node.args:
                val = self.evaluate(node.args[0])
                return val.upper() if isinstance(val, str) else val
            elif node.name == 'LOWER' and node.args:
                val = self.evaluate(node.args[0])
                return val.lower() if isinstance(val, str) else val
            elif node.name == 'COUNT' and not node.args:
                return 1
            else:
                return None

    def _get_column_from_expr(self, expr: ExprNode) -> str:
        """Извлечь имя колонки из выражения"""
        print(f"[DEBUG] _get_column_from_expr called with expr type: {type(expr)}")

        # Если expr - это список, берем первый элемент (для COUNT)
        if isinstance(expr, list):
            print(f"[DEBUG] expr is list, length: {len(expr)}")
            if expr:
                expr = expr[0]  # Берем первый элемент
                print(f"[DEBUG] Using first element: {type(expr)}")
            else:
                return "*"

        if isinstance(expr, IdentNode):
            print(f"[DEBUG] IdentNode.name = '{expr.name}'")
            return expr.name
        elif isinstance(expr, CompoundIdentNode):
            print(f"[DEBUG] CompoundIdentNode.full_name = '{expr.full_name}'")
            return expr.full_name
        elif isinstance(expr, StarNode):
            return "*"
        else:
            raise ValueError(f"Cannot extract column name from {type(expr)}: {expr}")
