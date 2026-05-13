from typing import Dict, Any, Optional, List

from SQL_compiler.execution.table import Table
from SQL_compiler.parsing.ast_nodes import *


class RowContext:
    def __init__(self, table: Table, row: Dict[str, Any], tables: Dict[str, Table] = None):
        self.table = table
        self.row = row
        self.row_index = -1
        self.tables = tables or {}
        self.table_aliases = {}
        if hasattr(table, 'aliases'):
            self.table_aliases = table.aliases

    def _convert_to_numeric(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            try:
                if '.' in stripped:
                    return float(stripped)
                else:
                    return int(stripped)
            except ValueError:
                return value
        return value

    def get_value(self, column_name: str) -> Any:
        if column_name in self.row:
            return self._convert_to_numeric(self.row[column_name])

        if "." in column_name:
            parts = column_name.split(".")
            if len(parts) == 2:
                table_or_alias = parts[0]
                col = parts[1]

                if column_name in self.row:
                    return self._convert_to_numeric(self.row[column_name])

                for key in self.row.keys():
                    if key == f"{table_or_alias}.{col}":
                        return self._convert_to_numeric(self.row[key])
                    if self.table_aliases.get(table_or_alias) and key == f"{self.table_aliases[table_or_alias]}.{col}":
                        return self._convert_to_numeric(self.row[key])

        base_name = column_name.split(".")[-1]

        if base_name in self.row:
            return self._convert_to_numeric(self.row[base_name])

        matches = [(key, val) for key, val in self.row.items()
                   if key.endswith(f".{base_name}")]

        if len(matches) == 1:
            return self._convert_to_numeric(matches[0][1])
        elif len(matches) > 1:
            for key, val in matches:
                key_table = key.split(".")[0]
                if key_table == column_name or key_table == base_name:
                    return self._convert_to_numeric(val)
                for alias, real_name in self.table_aliases.items():
                    if key_table == real_name or key_table == alias:
                        return self._convert_to_numeric(val)
            if matches:
                return self._convert_to_numeric(matches[0][1])
            raise Exception(f'Column "{column_name}" is ambiguous')

        for key in self.row.keys():
            if key.endswith(f".{base_name}"):
                return self._convert_to_numeric(self.row[key])

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

    def _convert_to_numeric(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            try:
                if '.' in stripped:
                    return float(stripped)
                else:
                    return int(stripped)
            except ValueError:
                return value
        return value

    def get_value(self, column_name: str) -> Any:
        if not self.rows:
            return None
        return self._convert_to_numeric(self._lookup_value(self.rows[0], column_name))

    def _lookup_value(self, row: Dict[str, Any], column: str) -> Any:
        if not isinstance(column, str):
            if hasattr(column, 'name'):
                column = column.name
            elif hasattr(column, 'full_name'):
                column = column.full_name
            else:
                column = str(column)

        if column in row:
            return row[column]
        if "." in column and column in row:
            return row[column]
        base_name = column.split(".")[-1]
        if base_name in row:
            return row[base_name]
        matches = [(key, val) for key, val in row.items() if key.endswith(f".{base_name}")]
        if len(matches) == 1:
            return matches[0][1]
        elif len(matches) > 1:
            for key, val in matches:
                if key.startswith(f"{base_name}."):
                    return val
        return None

    def get_aggregate(self, func_name: str, column: Optional[str] = None, distinct: bool = False) -> Any:
        from SQL_compiler.execution.function_manager import FunctionManager

        values = []
        for row in self.rows:
            if column:
                val = self._lookup_value(row, column)
                if isinstance(val, str):
                    try:
                        if '.' in val.strip():
                            val = float(val.strip())
                        else:
                            val = int(val.strip())
                    except ValueError:
                        pass
                values.append(val)
            else:
                values.append(1)

        return FunctionManager.call_aggregate(func_name, values, distinct)


class ExpressionEvaluator:
    _subquery_cache = {}
    _cache_enabled = True
    _execution_depth = 0
    _max_depth = 10

    def __init__(self, row_context: Optional[RowContext] = None, group_context: Optional[GroupContext] = None):
        self.row_context = row_context
        self.group_context = group_context

    @staticmethod
    def _to_numeric(value: Any) -> Any:
        if isinstance(value, str):
            try:
                if '.' in value.strip():
                    return float(value.strip())
                else:
                    return int(value.strip())
            except ValueError:
                return value
        return value

    def _ensure_numeric_types(self, left: Any, right: Any) -> tuple:
        left = self._to_numeric(left)
        right = self._to_numeric(right)

        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left, right

        if isinstance(left, (int, float)) and isinstance(right, str):
            try:
                right = float(right) if '.' in right else int(right)
            except ValueError:
                pass
        elif isinstance(left, str) and isinstance(right, (int, float)):
            try:
                left = float(left) if '.' in left else int(left)
            except ValueError:
                pass

        return left, right

    def evaluate(self, node: AstNode) -> Any:
        if isinstance(node, list):
            return [self.evaluate(item) for item in node if item is not None]

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
        elif isinstance(node, ConcatNode):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if left is None and right is None:
                return None
            left_str = str(left) if left is not None else ''
            right_str = str(right) if right is not None else ''
            return left_str + right_str
        elif isinstance(node, ExistsNode):
            from SQL_compiler.execution.executor import QueryExecutor
            tables = {}
            if self.row_context and hasattr(self.row_context, 'tables'):
                tables = self.row_context.tables
            executor = QueryExecutor(tables)
            result = executor.execute(node.subquery)
            exists = len(result) > 0
            return not exists if node.negated else exists
        elif isinstance(node, ScalarSubqueryNode):
            return self._evaluate_scalar_subquery(node)
        elif isinstance(node, UnionNode):
            from SQL_compiler.execution.executor import QueryExecutor
            tables = {}
            if self.row_context and hasattr(self.row_context, 'tables'):
                tables = self.row_context.tables
            executor = QueryExecutor(tables)
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
        elif self.group_context:
            if self.group_context.rows:
                return self.group_context.get_value(column_name)
            return None
        else:
            return None

    def _get_cache_key(self, subquery: SelectStmtNode, context_tables: Dict[str, Table]) -> str:
        tables_key = tuple(sorted(context_tables.keys()))
        return f"{str(subquery)}|{tables_key}"

    def _evaluate_in_subquery(self, node: InSubqueryNode) -> bool:
        left_value = self.evaluate(node.expr)

        tables = {}
        if self.row_context and hasattr(self.row_context, 'tables'):
            tables = self.row_context.tables

        cache_key = self._get_cache_key(node.subquery, tables)

        if cache_key in self._subquery_cache:
            right_values = self._subquery_cache[cache_key]
        else:
            from SQL_compiler.execution.executor import QueryExecutor
            executor = QueryExecutor(tables)

            try:
                subquery_rows = executor.execute(node.subquery)
                right_values = []
                for row in subquery_rows:
                    if row:
                        value = list(row.values())[0] if row else None
                        if value is not None:
                            if isinstance(value, str):
                                try:
                                    value = float(value) if '.' in value else int(value)
                                except ValueError:
                                    pass
                            right_values.append(value)
                if self._cache_enabled:
                    self._subquery_cache[cache_key] = right_values
            except Exception as e:
                print(f"Error executing subquery: {e}")
                right_values = []

        if isinstance(left_value, str):
            try:
                left_value = float(left_value) if '.' in left_value else int(left_value)
            except ValueError:
                pass

        result = left_value in right_values
        return not result if node.negated else result

    def _evaluate_scalar_subquery(self, node: ScalarSubqueryNode) -> Any:
        if ExpressionEvaluator._execution_depth >= ExpressionEvaluator._max_depth:
            print(f"Warning: Maximum subquery depth ({ExpressionEvaluator._max_depth}) exceeded")
            return None

        ExpressionEvaluator._execution_depth += 1

        try:
            tables = {}
            if self.row_context and hasattr(self.row_context, 'tables'):
                tables = self.row_context.tables

            cache_key = self._get_cache_key(node.subquery, tables)

            if self._cache_enabled and cache_key in self._subquery_cache:
                return self._subquery_cache[cache_key]

            from SQL_compiler.execution.executor import QueryExecutor
            executor = QueryExecutor(tables)

            result_rows = executor.execute(node.subquery)

            if not result_rows:
                return None

            first_row = result_rows[0]
            if first_row:
                first_value = list(first_row.values())[0] if first_row else None

                if isinstance(first_value, str):
                    try:
                        first_value = float(first_value) if '.' in first_value else int(first_value)
                    except ValueError:
                        pass

                if self._cache_enabled:
                    self._subquery_cache[cache_key] = first_value

                return first_value

            return None
        except Exception as e:
            print(f"Error executing scalar subquery: {e}")
            return None
        finally:
            ExpressionEvaluator._execution_depth -= 1

    def _evaluate_in(self, node: InNode) -> bool:
        left_value = self.evaluate(node.expr)
        right_values = [self.evaluate(elem) for elem in node.elements]

        if isinstance(left_value, str):
            try:
                left_value = float(left_value) if '.' in left_value else int(left_value)
            except ValueError:
                pass

        right_values_converted = []
        for v in right_values:
            if isinstance(v, str):
                try:
                    v = float(v) if '.' in v else int(v)
                except ValueError:
                    pass
            right_values_converted.append(v)

        result = left_value in right_values_converted
        return not result if node.negated else result

    def _evaluate_between(self, node: BetweenNode) -> bool:
        value = self.evaluate(node.expr)
        low = self.evaluate(node.low)
        high = self.evaluate(node.high)

        value = self._to_numeric(value)
        low = self._to_numeric(low)
        high = self._to_numeric(high)

        if value is None or low is None or high is None:
            return False if node.negated else False
        try:
            result = low <= value <= high
        except TypeError:
            result = str(low) <= str(value) <= str(high)

        return not result if node.negated else result

    def _evaluate_is_null(self, node: IsNullNode) -> bool:
        value = self.evaluate(node.expr)
        result = value is None
        return not result if node.negated else result

    def _evaluate_binop(self, node: BinOpNode) -> Any:
        left = self.evaluate(node.arg1)
        right = self.evaluate(node.arg2)

        if left is None or right is None:
            if node.op in (BinOp.EQ, BinOp.NE, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
                return None
            return None

        if node.op in (BinOp.ADD, BinOp.SUB, BinOp.MUL, BinOp.DIV, BinOp.REM):
            left, right = self._ensure_numeric_types(left, right)

        if node.op in (BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE, BinOp.EQ, BinOp.NE, BinOp.NE2):
            if isinstance(left, str) and isinstance(right, (int, float)):
                try:
                    left = float(left) if '.' in left else int(left)
                except ValueError:
                    pass
            elif isinstance(left, (int, float)) and isinstance(right, str):
                try:
                    right = float(right) if '.' in right else int(right)
                except ValueError:
                    pass

        try:
            if node.op == BinOp.ADD:
                return left + right
            elif node.op == BinOp.SUB:
                return left - right
            elif node.op == BinOp.MUL:
                return left * right
            elif node.op == BinOp.DIV:
                if right == 0:
                    return float('inf')
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
            elif node.op == BinOp.NE or node.op == BinOp.NE2:
                return left != right
            elif node.op == BinOp.AND:
                if left is None or right is None:
                    if left is False or right is False:
                        return False
                    return None
                return left and right
            elif node.op == BinOp.OR:
                if left is None or right is None:
                    if left is True or right is True:
                        return True
                    return None
                return left or right
            elif node.op == BinOp.LIKE:
                return self._evaluate_like(str(left), str(right))
            elif node.op == BinOp.NOT_LIKE:
                return not self._evaluate_like(str(left), str(right))
            else:
                raise ValueError(f"Unknown operator: {node.op}")
        except TypeError as e:
            print(f"Type error in binary operation: {e}")
            return None

    def _evaluate_like(self, value: str, pattern: str) -> bool:
        if not isinstance(value, str) or not isinstance(pattern, str):
            return False

        import re
        regex_pattern = re.escape(pattern).replace('%', '.*').replace('_', '.')
        return re.match(f"^{regex_pattern}$", value, re.IGNORECASE) is not None

    def _evaluate_unop(self, node: UnOpNode) -> Any:
        arg = self.evaluate(node.arg)

        if node.op in (UnOp.PLUS, UnOp.MINUS):
            arg = self._to_numeric(arg)

        if node.op == UnOp.NOT:
            if arg is None:
                return None
            return not arg
        elif node.op == UnOp.PLUS:
            return +arg if arg is not None else None
        elif node.op == UnOp.MINUS:
            return -arg if arg is not None else None
        else:
            raise ValueError(f"Unknown unary operator: {node.op}")

    def _make_hashable(self, value: Any) -> Any:
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
        from SQL_compiler.execution.function_manager import FunctionManager

        if self.group_context and FunctionManager.is_aggregate(node.name):
            if node.name.upper() == 'COUNT' and (
                    not node.args or (len(node.args) == 1 and isinstance(node.args[0], StarNode))):
                return len(self.group_context.rows)
            else:
                column = self._get_column_from_expr(node.args[0]) if node.args else None
                return self.group_context.get_aggregate(node.name, column, node.distinct)

        args = []
        for arg in node.args:
            if isinstance(arg, StarNode):
                continue
            evaluated = self.evaluate(arg)
            if isinstance(evaluated, str):
                try:
                    evaluated = float(evaluated) if '.' in evaluated else int(evaluated)
                except ValueError:
                    pass
            args.append(evaluated)

        try:
            result = FunctionManager.call(node.name, *args)
            return result
        except ValueError as e:
            print(f"Warning: {e}")
            return None

    def _get_column_from_expr(self, expr: ExprNode) -> str:
        if isinstance(expr, list):
            if expr:
                expr = expr[0]
            else:
                return "*"

        if isinstance(expr, IdentNode):
            return expr.name
        elif isinstance(expr, CompoundIdentNode):
            return expr.full_name
        elif isinstance(expr, StarNode):
            return "*"
        else:
            raise ValueError(f"Cannot extract column name from {type(expr)}: {expr}")