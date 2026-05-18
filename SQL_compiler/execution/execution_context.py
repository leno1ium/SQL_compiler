from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib
import json

from SQL_compiler.execution.table import Table
from SQL_compiler.parsing.ast_nodes import *

FunctionManager = None


class RowContext:
    def __init__(self, table: Table, row: Dict[str, Any], tables: Dict[str, Table] = None,
                 outer_context: Optional['RowContext'] = None):
        self.table = table
        self.row = row
        self.tables = tables or {}
        self.outer_context = outer_context
        self.table_aliases = getattr(table, 'aliases', {})
        self._scalar_cache = {}

    def get_value(self, column_name: str) -> Any:
        # Быстрый поиск
        if column_name in self.row:
            return self.row[column_name]

        # Поиск с префиксом таблицы
        if "." in column_name:
            parts = column_name.split(".")
            if len(parts) == 2:
                table_alias, col = parts
                for key in self.row:
                    if key == f"{table_alias}.{col}":
                        return self.row[key]
                    if self.table_aliases.get(table_alias) and key == f"{self.table_aliases[table_alias]}.{col}":
                        return self.row[key]

        # Поиск по базовому имени
        base_name = column_name.split(".")[-1]
        if base_name in self.row:
            return self.row[base_name]

        # Поиск в конце ключа
        for key, val in self.row.items():
            if key.endswith(f".{base_name}"):
                return val

        # Коррелированный подзапрос - поиск во внешнем контексте
        if self.outer_context:
            return self.outer_context.get_value(column_name)

        return None

    def get_type(self, column_name: str) -> type:
        try:
            if "." in column_name:
                base_name = column_name.split(".")[-1]
                return self.table.get_column_type(base_name)
            return self.table.get_column_type(column_name)
        except KeyError:
            if self.outer_context:
                return self.outer_context.get_type(column_name)
            return str

    def get_scalar_cache(self, key: str) -> Any:
        return self._scalar_cache.get(key)

    def set_scalar_cache(self, key: str, value: Any):
        self._scalar_cache[key] = value


class GroupContext:
    def __init__(self, rows: List[Dict[str, Any]]):
        self.rows = rows

    def get_value(self, column_name: str) -> Any:
        if not self.rows:
            return None
        return self._lookup_value(self.rows[0], column_name)

    def _lookup_value(self, row: Dict[str, Any], column: str) -> Any:
        if not isinstance(column, str):
            column = getattr(column, 'name', getattr(column, 'full_name', str(column)))

        if column in row:
            return row[column]

        base_name = column.split(".")[-1]
        if base_name in row:
            return row[base_name]

        for key, val in row.items():
            if key.endswith(f".{base_name}"):
                return val
        return None

    def get_aggregate(self, func_name: str, column: Optional[str] = None, distinct: bool = False) -> Any:
        global FunctionManager
        if FunctionManager is None:
            from SQL_compiler.execution.function_manager import FunctionManager as FM
            FunctionManager = FM

        values = []
        for row in self.rows:
            if column and column != '*':
                val = self._lookup_value(row, column)
                if val is not None:
                    values.append(val)
            else:
                values.append(1)

        if not values:
            if func_name.upper() == 'COUNT':
                return 0
            return None

        return FunctionManager.call_aggregate(func_name, values, distinct)


class ExpressionEvaluator:
    _subquery_cache = {}
    _cache_enabled = True
    _recursion_depth = 0
    _max_depth = 3

    def __init__(self, row_context: Optional[RowContext] = None, group_context: Optional[GroupContext] = None):
        self.row_context = row_context
        self.group_context = group_context

    @classmethod
    def clear_cache(cls):
        cls._subquery_cache = {}
        cls._recursion_depth = 0

    def _parse_date_string(self, value: str) -> Any:
        """Преобразование строки в дату с поддержкой разных форматов"""
        if not isinstance(value, str):
            return value

        if len(value) >= 2 and value[0] in '\'"' and value[-1] in '\'"':
            value = value[1:-1]

        value = value.strip()

        # Если уже в формате YYYY-MM-DD
        if len(value) == 10 and value[4] == '-' and value[7] == '-':
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                pass

        # Все поддерживаемые форматы
        formats = [
            "%Y-%m-%d",  # 2000-01-10
            "%d.%m.%Y",  # 10.01.2000
            "%Y/%m/%d",  # 2000/01/10
            "%d-%m-%Y",  # 10-01-2000
            "%m/%d/%Y",  # 01/10/2000 (американский)
            "%d/%m/%Y",  # 10/01/2000 (европейский)
            "%d.%m.%y",  # 10.01.00
            "%Y%m%d",  # 20000110
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        return value

    def evaluate(self, node: AstNode) -> Any:
        if node is None:
            return None

        if isinstance(node, list):
            return [self.evaluate(item) for item in node if item is not None]

        if isinstance(node, NumNode):
            return node.num
        elif isinstance(node, StringNode):
            return self._parse_date_string(node.value)
        elif isinstance(node, BoolNode):
            return node.value
        elif isinstance(node, NullNode):
            return None
        elif isinstance(node, (IdentNode, CompoundIdentNode)):
            name = getattr(node, 'full_name', getattr(node, 'name', str(node)))
            return self._get_column_value(name)
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
            value = self.evaluate(node.expr)
            result = value is None
            return not result if node.negated else result
        elif isinstance(node, FuncCallNode):
            return self._evaluate_function(node)
        elif isinstance(node, StarNode):
            raise ValueError("StarNode can only be used in SELECT list")
        elif isinstance(node, ConcatNode):
            left = self.evaluate(node.left) or ''
            right = self.evaluate(node.right) or ''
            return str(left) + str(right)
        elif isinstance(node, ExistsNode):
            return self._evaluate_exists(node)
        elif isinstance(node, ScalarSubqueryNode):
            return self._evaluate_scalar_subquery(node)
        elif isinstance(node, UnionNode):
            from SQL_compiler.execution.executor import QueryExecutor
            tables = getattr(self.row_context, 'tables', {})
            executor = QueryExecutor(tables, self.row_context)
            left_result = executor.execute(node.left)
            right_result = executor.execute(node.right)
            return left_result + right_result if node.all else self._union_unique(left_result, right_result)
        else:
            raise ValueError(f"Unknown node type: {type(node)}")

    def _union_unique(self, left: List[Dict], right: List[Dict]) -> List[Dict]:
        seen = set()
        result = []
        for row in left + right:
            row_tuple = tuple(sorted(row.items()))
            if row_tuple not in seen:
                seen.add(row_tuple)
                result.append(row)
        return result

    def _get_column_value(self, column_name: str) -> Any:
        if self.row_context:
            return self.row_context.get_value(column_name)
        elif self.group_context and self.group_context.rows:
            return self.group_context._lookup_value(self.group_context.rows[0], column_name)
        return None

    def _get_cache_key(self, subquery: SelectStmtNode) -> str:
        """Генерация уникального ключа для кэша подзапроса"""
        # Базовый ключ
        key = str(id(subquery))

        # Для коррелированных подзапросов добавляем хеш текущей строки
        if self.row_context and self.row_context.row:
            # Создаем хеш значений текущей строки
            row_values = []
            for col, val in sorted(self.row_context.row.items()):
                if col.startswith('__'):
                    continue
                row_values.append(f"{col}={val}")
            row_hash = hashlib.md5('|'.join(row_values).encode()).hexdigest()
            key = f"{key}|{row_hash}"

        return key

    def _is_correlated(self, subquery: SelectStmtNode) -> bool:
        """Проверить, является ли подзапрос коррелированным"""
        if not self.row_context:
            return False

        # Простая проверка: ищем ссылки на внешние колонки
        outer_columns = set(self.row_context.row.keys())

        def check_correlation(node):
            if isinstance(node, (IdentNode, CompoundIdentNode)):
                name = getattr(node, 'full_name', getattr(node, 'name', str(node)))
                base_name = name.split('.')[-1]
                if base_name in outer_columns:
                    return True
            for child in node.childs:
                if check_correlation(child):
                    return True
            return False

        return check_correlation(subquery)

    def _evaluate_exists(self, node: ExistsNode) -> bool:
        from SQL_compiler.execution.executor import QueryExecutor

        # Для коррелированных подзапросов не используем кэш
        is_correlated = self._is_correlated(node.subquery)
        cache_key = None if is_correlated else self._get_cache_key(node.subquery)

        if not is_correlated and cache_key in self._subquery_cache:
            result = self._subquery_cache[cache_key]
        else:
            tables = getattr(self.row_context, 'tables', {})
            executor = QueryExecutor(tables, self.row_context)
            executor.limit = 1
            result = len(executor.execute(node.subquery)) > 0

            if not is_correlated and self._cache_enabled:
                self._subquery_cache[cache_key] = result

        return not result if node.negated else result

    def _evaluate_in_subquery(self, node: InSubqueryNode) -> bool:
        left_value = self.evaluate(node.expr)

        # Для коррелированных подзапросов не используем кэш
        is_correlated = self._is_correlated(node.subquery)
        cache_key = None if is_correlated else self._get_cache_key(node.subquery)

        if not is_correlated and cache_key in self._subquery_cache:
            right_set = self._subquery_cache[cache_key]
        else:
            from SQL_compiler.execution.executor import QueryExecutor
            tables = getattr(self.row_context, 'tables', {})
            executor = QueryExecutor(tables, self.row_context)
            subquery_rows = executor.execute(node.subquery)

            right_set = set()
            for row in subquery_rows:
                if row:
                    value = next(iter(row.values())) if row else None
                    if value is not None:
                        right_set.add(value)

            if not is_correlated and self._cache_enabled:
                self._subquery_cache[cache_key] = right_set

        result = left_value in right_set
        return not result if node.negated else result

    def _evaluate_scalar_subquery(self, node: ScalarSubqueryNode) -> Any:
        if ExpressionEvaluator._recursion_depth >= ExpressionEvaluator._max_depth:
            return None

        ExpressionEvaluator._recursion_depth += 1

        try:
            from SQL_compiler.execution.executor import QueryExecutor
            tables = getattr(self.row_context, 'tables', {})
            executor = QueryExecutor(tables, self.row_context)
            result_rows = executor.execute(node.subquery)

            # Возвращаем список всех значений для коррелированных подзапросов
            if result_rows:
                values = []
                for row in result_rows:
                    if row:
                        value = next(iter(row.values())) if row else None
                        if value is not None:
                            values.append(value)
                return values if len(values) > 1 else (values[0] if values else None)
            return None
        finally:
            ExpressionEvaluator._recursion_depth -= 1

    def _evaluate_in(self, node: InNode) -> bool:
        left_value = self.evaluate(node.expr)
        for elem in node.elements:
            if left_value == self.evaluate(elem):
                return not node.negated
        return node.negated

    def _evaluate_between(self, node: BetweenNode) -> bool:
        value = self.evaluate(node.expr)
        low = self.evaluate(node.low)
        high = self.evaluate(node.high)

        if value is None or low is None or high is None:
            return False

        try:
            result = low <= value <= high
        except TypeError:
            result = False

        return not result if node.negated else result

    def _evaluate_binop(self, node: BinOpNode) -> Any:
        left = self.evaluate(node.arg1)
        right = self.evaluate(node.arg2)

        # Обработка списка (результат подзапроса с несколькими строками)
        if isinstance(right, list):
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2):
                # = ANY или IN - проверяем вхождение
                if node.op == BinOp.EQ:
                    return left in right
                elif node.op in (BinOp.NE, BinOp.NE2):
                    return left not in right
            elif node.op in (BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
                # Для сравнений >, < и т.д. - берем первый элемент
                right = right[0] if right else None
                if right is None:
                    return None
            else:
                return None

        # Обработка левой части как списка
        if isinstance(left, list):
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2):
                if node.op == BinOp.EQ:
                    return right in left
                elif node.op in (BinOp.NE, BinOp.NE2):
                    return right not in left
            else:
                left = left[0] if left else None
                if left is None:
                    return None

        # NULL handling - по SQL NULL в сравнениях дает NULL (False в WHERE)
        if left is None or right is None:
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
                return None
            elif node.op == BinOp.AND:
                if left is False or right is False:
                    return False
                return None
            elif node.op == BinOp.OR:
                if left is True or right is True:
                    return True
                return None
            return None

        # Приведение типов для сравнения
        if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
            # Приводим строки к датам если нужно
            if isinstance(left, str) and isinstance(right, datetime):
                left = self._parse_date_string(left)
            elif isinstance(right, str) and isinstance(left, datetime):
                right = self._parse_date_string(right)

            # Приводим строки к числам если нужно
            if isinstance(left, str) and isinstance(right, (int, float)):
                try:
                    left = float(left) if '.' in left else int(left)
                except ValueError:
                    pass
            elif isinstance(right, str) and isinstance(left, (int, float)):
                try:
                    right = float(right) if '.' in right else int(right)
                except ValueError:
                    pass

        # Date comparison
        if isinstance(left, datetime) and isinstance(right, datetime):
            return self._compare_dates(left, right, node.op)

        # String comparison
        if isinstance(left, str) and isinstance(right, str):
            if node.op == BinOp.LIKE:
                return self._evaluate_like(left, right)
            elif node.op == BinOp.NOT_LIKE:
                return not self._evaluate_like(left, right)

        # Numeric operations
        try:
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
            elif node.op in (BinOp.NE, BinOp.NE2):
                return left != right
            elif node.op == BinOp.AND:
                return left and right
            elif node.op == BinOp.OR:
                return left or right
        except TypeError:
            return None

        raise ValueError(f"Unknown operator: {node.op}")

    def _compare_dates(self, left: datetime, right: datetime, op: BinOp) -> bool:
        if op == BinOp.EQ:
            return left == right
        elif op in (BinOp.NE, BinOp.NE2):
            return left != right
        elif op == BinOp.GT:
            return left > right
        elif op == BinOp.GE:
            return left >= right
        elif op == BinOp.LT:
            return left < right
        elif op == BinOp.LE:
            return left <= right
        return False

    def _evaluate_like(self, value: str, pattern: str) -> bool:
        if not isinstance(value, str) or not isinstance(pattern, str):
            return False

        import re
        pattern = pattern.replace('%', '.*').replace('_', '.')
        pattern = re.escape(pattern).replace('\\.\\*', '.*').replace('\\.', '.')
        return re.match(f"^{pattern}$", value, re.IGNORECASE) is not None

    def _evaluate_unop(self, node: UnOpNode) -> Any:
        arg = self.evaluate(node.arg)

        if node.op == UnOp.NOT:
            return not arg if arg is not None else None
        elif node.op == UnOp.PLUS:
            return +arg if arg is not None else None
        elif node.op == UnOp.MINUS:
            return -arg if arg is not None else None
        return None

    def _evaluate_function(self, node: FuncCallNode) -> Any:
        global FunctionManager
        if FunctionManager is None:
            from SQL_compiler.execution.function_manager import FunctionManager as FM
            FunctionManager = FM

        if self.group_context and FunctionManager.is_aggregate(node.name):
            if node.name.upper() == 'COUNT' and (not node.args or isinstance(node.args[0], StarNode)):
                return len(self.group_context.rows)
            column = self._get_column_from_expr(node.args[0]) if node.args else None
            return self.group_context.get_aggregate(node.name, column, node.distinct)

        args = []
        for arg in node.args:
            if isinstance(arg, StarNode):
                continue
            evaluated = self.evaluate(arg)
            args.append(evaluated)

        try:
            # Для SUBSTR с 2 или 3 аргументами
            if node.name.upper() == 'SUBSTR' and len(args) >= 2:
                # Преобразуем start в int (1-индексация)
                if args[1] is not None:
                    args[1] = int(args[1]) if isinstance(args[1], (int, float)) else 1
                if len(args) >= 3 and args[2] is not None:
                    args[2] = int(args[2]) if isinstance(args[2], (int, float)) else None

            # Для ROUND с отрицательными значениями
            if node.name.upper() == 'ROUND' and len(args) >= 2 and args[1] is not None:
                args[1] = int(args[1])

            result = FunctionManager.call(node.name, *args)
            return result
        except ValueError as e:
            print(f"Warning: {e}")
            return None

    def _get_column_from_expr(self, expr: ExprNode) -> str:
        if isinstance(expr, list):
            expr = expr[0] if expr else None
        if isinstance(expr, IdentNode):
            return expr.name
        elif isinstance(expr, CompoundIdentNode):
            return expr.full_name
        return "*"
