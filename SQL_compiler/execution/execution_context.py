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
        normalized_name = column_name.replace('...', '.').replace('..', '.')

        # 1. Точное совпадение в текущей строке
        if normalized_name in self.row:
            return self.row[normalized_name]

        # 2. Если есть префикс таблицы (S.UNIV_ID)
        if "." in normalized_name:
            parts = normalized_name.split(".")
            if len(parts) == 2:
                table_alias, col = parts

                alias_key = f"{table_alias}.{col}"

                table_found = False
                for key in self.row:
                    if key.startswith(f"{table_alias}."):
                        table_found = True
                        break

                if not table_found and self.outer_context:
                    value = self.outer_context.get_value(normalized_name)
                    if value is not None:
                        return value

                if alias_key in self.row:
                    return self.row[alias_key]

        # 3. Поиск по базовому имени (без префикса)
        base_name = normalized_name.split(".")[-1]

        matching_keys = [k for k in self.row if k.endswith(f".{base_name}") or k == base_name]

        if len(matching_keys) == 1 and matching_keys[0] in self.row:
            return self.row[matching_keys[0]]

        if self.outer_context:
            value = self.outer_context.get_value(column_name)
            if value is not None:
                return value

            value = self.outer_context.get_value(base_name)
            if value is not None:
                return value

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
    _correlated_cache = {}
    _cache_enabled = True
    _recursion_depth = 0
    _max_depth = 5

    def __init__(self, row_context: Optional[RowContext] = None, group_context: Optional[GroupContext] = None):
        self.row_context = row_context
        self.group_context = group_context

    @classmethod
    def clear_cache(cls):
        cls._subquery_cache.clear()
        cls._correlated_cache.clear()
        cls._recursion_depth = 0

    def _to_datetime(self, value: Any) -> Any:
        """Преобразует строку в datetime, если возможно, иначе возвращает исходное значение."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in [
                "%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y",
                "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%Y%m%d"
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return value

    def _extract_correlation_columns(self, subquery: SelectStmtNode) -> List[str]:
        outer_cols = set()
        if not self.row_context:
            return []
        outer_row_keys = set(self.row_context.row.keys())
        outer_base_names = {k.split('.')[-1] for k in outer_row_keys}

        def find_outer(node):
            if node is None:
                return
            if isinstance(node, IdentNode):
                name = node.name
                if name in outer_row_keys:
                    outer_cols.add(name)
                elif name in outer_base_names:
                    for key in outer_row_keys:
                        if key.endswith(f".{name}") or key == name:
                            outer_cols.add(key)
                            break
            elif isinstance(node, CompoundIdentNode):
                full = node.full_name
                if full in outer_row_keys:
                    outer_cols.add(full)
            for child in node.childs:
                find_outer(child)

        find_outer(subquery.where_clause)
        return list(outer_cols)

    def _get_correlated_cache_key(self, subquery: SelectStmtNode) -> str:
        if not self.row_context or not self.row_context.row:
            return str(id(subquery))

        outer_cols = self._extract_correlation_columns(subquery)
        if not outer_cols:
            outer_cols = [k for k in self.row_context.row.keys() if not k.startswith('__')]

        key_parts = [str(id(subquery))]
        for col in sorted(outer_cols):
            val = self.row_context.get_value(col)
            if val is None:
                key_parts.append(f"{col}=None")
            elif isinstance(val, datetime):
                key_parts.append(f"{col}={val.isoformat()}")
            else:
                key_parts.append(f"{col}={str(val)}")
        return '|'.join(key_parts)

    def _parse_date_string(self, value: str) -> Any:
        return self._to_datetime(value)

    def evaluate(self, node: AstNode) -> Any:
        if node is None:
            return None
        if isinstance(node, list):
            return [self.evaluate(item) for item in node if item is not None]
        if isinstance(node, NumNode):
            return node.num
        elif isinstance(node, AllAnyNode):
            return self._evaluate_all_any(node)
        elif isinstance(node, StarNode):
            raise ValueError("StarNode can only be used in SELECT list")
        elif isinstance(node, QualifiedStarNode):
            raise ValueError("QualifiedStarNode can only be used in SELECT list")
        elif isinstance(node, StringNode):
            return self._to_datetime(node.value)
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
            if node.all:
                return left_result + right_result
            else:
                seen = set()
                result = []
                for row in left_result + right_result:
                    row_tuple = tuple(sorted(row.items()))
                    if row_tuple not in seen:
                        seen.add(row_tuple)
                        result.append(row)
                return result
        else:
            raise ValueError(f"Unknown node type: {type(node)}")

    def _get_column_value(self, column_name: str) -> Any:
        if self.row_context:
            return self.row_context.get_value(column_name)
        elif self.group_context and self.group_context.rows:
            return self.group_context._lookup_value(self.group_context.rows[0], column_name)
        return None

    def _get_cache_key(self, subquery: SelectStmtNode) -> str:
        return str(id(subquery))

    def _is_correlated(self, subquery: SelectStmtNode) -> bool:
        if not self.row_context:
            return False
        outer_columns = set()
        for key in self.row_context.row.keys():
            if not key.startswith('__'):
                outer_columns.add(key.split('.')[-1])

        def check_correlation(node):
            if node is None:
                return False
            if isinstance(node, (IdentNode, CompoundIdentNode)):
                name = getattr(node, 'full_name', getattr(node, 'name', str(node)))
                outer_full = set(self.row_context.row.keys())
                outer_base = {k.split('.')[-1] for k in outer_full}
                if name in outer_full:
                    return True
                base_name = name.split('.')[-1]
                if base_name in outer_base:
                    return True
            for child in node.childs:
                if check_correlation(child):
                    return True
            return False
        return check_correlation(subquery)

    def _evaluate_exists(self, node: ExistsNode) -> bool:
        from SQL_compiler.execution.executor import QueryExecutor

        tables = getattr(self.row_context, 'tables', {})
        is_correlated = self._is_correlated(node.subquery)
        cache_key = None
        if is_correlated:
            cache_key = self._get_correlated_cache_key(node.subquery)
            if cache_key in self._correlated_cache:
                return self._correlated_cache[cache_key]

        executor = QueryExecutor(tables, self.row_context)
        executor.limit = 1
        executor.exists_mode = True

        try:
            subquery_rows = executor.execute(node.subquery)
            result = len(subquery_rows) > 0
            result = not result if node.negated else result
            if is_correlated and cache_key:
                self._correlated_cache[cache_key] = result
            return result
        except Exception as e:
            print(f"EXISTS error: {e}")
            return False

    def _evaluate_all_any(self, node: AllAnyNode) -> bool:
        left_value = self.evaluate(node.expr)
        is_correlated = self._is_correlated(node.subquery)
        cache_key = None
        if is_correlated:
            cache_key = self._get_correlated_cache_key(node.subquery)
            if cache_key in self._correlated_cache:
                return self._correlated_cache[cache_key]

        if not is_correlated:
            cache_key = self._get_cache_key(node.subquery)
            if cache_key in self._subquery_cache:
                right_values = self._subquery_cache[cache_key]
            else:
                right_values = self._execute_subquery_values(node.subquery)
                if self._cache_enabled:
                    self._subquery_cache[cache_key] = right_values
        else:
            right_values = self._execute_subquery_values(node.subquery)

        if not right_values:
            result = node.all_any == 'ALL'
            if is_correlated and cache_key:
                self._correlated_cache[cache_key] = result
            return result

        operator = node.operator
        if node.all_any == 'ALL':
            if operator == '<':
                result = all(left_value < val for val in right_values)
            elif operator == '<=':
                result = all(left_value <= val for val in right_values)
            elif operator == '>':
                result = all(left_value > val for val in right_values)
            elif operator == '>=':
                result = all(left_value >= val for val in right_values)
            elif operator == '=':
                result = all(left_value == val for val in right_values)
            elif operator in ('!=', '<>'):
                result = all(left_value != val for val in right_values)
            else:
                result = False
        else:
            if operator == '<':
                result = any(left_value < val for val in right_values)
            elif operator == '<=':
                result = any(left_value <= val for val in right_values)
            elif operator == '>':
                result = any(left_value > val for val in right_values)
            elif operator == '>=':
                result = any(left_value >= val for val in right_values)
            elif operator == '=':
                result = any(left_value == val for val in right_values)
            elif operator in ('!=', '<>'):
                result = any(left_value != val for val in right_values)
            else:
                result = False

        if is_correlated and cache_key:
            self._correlated_cache[cache_key] = result
        return result

    def _execute_subquery_values(self, subquery: SelectStmtNode) -> List[Any]:
        from SQL_compiler.execution.executor import QueryExecutor
        tables = getattr(self.row_context, 'tables', {})
        executor = QueryExecutor(tables, self.row_context)
        subquery_rows = executor.execute(subquery)
        values = []
        for row in subquery_rows:
            if row:
                value = next(iter(row.values())) if row else None
                if value is not None:
                    values.append(value)
        return values

    def _evaluate_in_subquery(self, node: InSubqueryNode) -> bool:
        left_value = self.evaluate(node.expr)
        is_correlated = self._is_correlated(node.subquery)
        cache_key = None
        if is_correlated:
            cache_key = self._get_correlated_cache_key(node.subquery)
            if cache_key in self._correlated_cache:
                right_set = self._correlated_cache[cache_key]
            else:
                right_set = self._execute_subquery_set(node.subquery)
                self._correlated_cache[cache_key] = right_set
        else:
            cache_key = self._get_cache_key(node.subquery)
            if cache_key in self._subquery_cache:
                right_set = self._subquery_cache[cache_key]
            else:
                right_set = self._execute_subquery_set(node.subquery)
                if self._cache_enabled:
                    self._subquery_cache[cache_key] = right_set

        result = left_value in right_set
        return not result if node.negated else result

    def _execute_subquery_set(self, subquery: SelectStmtNode) -> set:
        from SQL_compiler.execution.executor import QueryExecutor
        tables = getattr(self.row_context, 'tables', {})
        executor = QueryExecutor(tables, self.row_context)
        subquery_rows = executor.execute(subquery)
        result_set = set()
        for row in subquery_rows:
            if row:
                value = next(iter(row.values())) if row else None
                if value is not None:
                    result_set.add(value)
        return result_set

    def _evaluate_scalar_subquery(self, node: ScalarSubqueryNode) -> Any:
        if self._recursion_depth >= self._max_depth:
            return None

        is_correlated = self._is_correlated(node.subquery)
        cache_key = None
        if is_correlated:
            cache_key = self._get_correlated_cache_key(node.subquery)
            if cache_key in self._correlated_cache:
                return self._correlated_cache[cache_key]
        else:
            cache_key = self._get_cache_key(node.subquery)
            if cache_key in self._subquery_cache:
                return self._subquery_cache[cache_key]

        self._recursion_depth += 1
        try:
            from SQL_compiler.execution.executor import QueryExecutor
            tables = getattr(self.row_context, 'tables', {})
            executor = QueryExecutor(tables, self.row_context)
            result_rows = executor.execute(node.subquery)
            if result_rows:
                first_row = result_rows[0]
                value = next(iter(first_row.values())) if first_row else None
            else:
                value = None

            if is_correlated and cache_key:
                self._correlated_cache[cache_key] = value
            elif not is_correlated and self._cache_enabled:
                self._subquery_cache[cache_key] = value
            return value
        finally:
            self._recursion_depth -= 1

    def _evaluate_between(self, node: BetweenNode) -> bool:
        expr = self.evaluate(node.expr)
        low = self.evaluate(node.low)
        high = self.evaluate(node.high)

        if isinstance(expr, datetime) or isinstance(low, datetime) or isinstance(high, datetime):
            expr = self._to_datetime(expr)
            low = self._to_datetime(low)
            high = self._to_datetime(high)

        if expr is None or low is None or high is None:
            return False

        try:
            result = low <= expr <= high
        except TypeError:
            try:
                result = str(low) <= str(expr) <= str(high)
            except:
                result = False

        return not result if node.negated else result

    def _evaluate_binop(self, node: BinOpNode) -> Any:
        if isinstance(node.arg1, ScalarSubqueryNode):
            left = self._evaluate_scalar_subquery(node.arg1)
        elif isinstance(node.arg1, ExistsNode):
            left = self._evaluate_exists(node.arg1)
        else:
            left = self.evaluate(node.arg1)

        if isinstance(node.arg2, ScalarSubqueryNode):
            right = self._evaluate_scalar_subquery(node.arg2)
        elif isinstance(node.arg2, ExistsNode):
            right = self._evaluate_exists(node.arg2)
        else:
            right = self.evaluate(node.arg2)

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

        if isinstance(right, list):
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2):
                if node.op == BinOp.EQ:
                    return left in right
                elif node.op in (BinOp.NE, BinOp.NE2):
                    return left not in right
            elif node.op in (BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
                right = right[0] if right else None
                if right is None:
                    return None
            else:
                return None

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

        # Приведение типов для сравнений
        if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
            if isinstance(left, datetime) and isinstance(right, str):
                right = self._to_datetime(right)
            elif isinstance(right, datetime) and isinstance(left, str):
                left = self._to_datetime(left)
            elif isinstance(left, str) and isinstance(right, str):
                left_dt = self._to_datetime(left)
                right_dt = self._to_datetime(right)
                if isinstance(left_dt, datetime) and isinstance(right_dt, datetime):
                    left, right = left_dt, right_dt

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

        if isinstance(left, datetime) and isinstance(right, datetime):
            return self._compare_dates(left, right, node.op)

        if isinstance(left, str) and isinstance(right, str):
            if node.op == BinOp.LIKE:
                return self._evaluate_like(left, right)
            elif node.op == BinOp.NOT_LIKE:
                return not self._evaluate_like(left, right)

        try:
            if node.op == BinOp.ADD:
                return left + right
            elif node.op == BinOp.SUB:
                return left - right
            elif node.op == BinOp.MUL:
                return left * right
            elif node.op == BinOp.DIV:
                if right == 0:
                    return None
                if isinstance(left, int) and isinstance(right, int):
                    return left // right
                return left / right
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
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.NE2):
                return str(left) == str(right) if node.op == BinOp.EQ else str(left) != str(right)
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
        if isinstance(node.arg, ExistsNode):
            arg = self._evaluate_exists(node.arg)
        else:
            arg = self.evaluate(node.arg)
        if node.op == UnOp.NOT:
            return not arg if arg is not None else None
        elif node.op == UnOp.PLUS:
            return +arg if arg is not None else None
        elif node.op == UnOp.MINUS:
            return -arg if arg is not None else None
        return None

    def _evaluate_in(self, node: InNode) -> bool:
        left_value = self.evaluate(node.expr)
        for elem in node.elements:
            if left_value == self.evaluate(elem):
                return not node.negated
        return node.negated

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
            if node.name.upper() == 'SUBSTR' and len(args) >= 2:
                if args[1] is not None:
                    args[1] = int(args[1]) if isinstance(args[1], (int, float)) else 1
                if len(args) >= 3 and args[2] is not None:
                    args[2] = int(args[2]) if isinstance(args[2], (int, float)) else None
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