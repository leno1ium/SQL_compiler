from typing import Dict, Any, Optional, List

from SQL_compiler.executor.table import Table
from SQL_compiler.parser.ast_nodes import *


class RowContext:
    def __init__(self, table: Table, row: Dict[str, Any]):
        self.table = table
        self.row = row
        self.row_index = -1

    def get_value(self, column_name: str) -> Any:
        if column_name in self.row:
            return self.row.get(column_name)

        if "." in column_name and column_name in self.row:
            return self.row.get(column_name)

        if "." in column_name:
            base_name = column_name.split(".")[-1]
        else:
            base_name = column_name

        if base_name in self.row:
            return self.row.get(base_name)

        matches = []
        for key in self.row.keys():
            if key.endswith(f".{base_name}"):
                matches.append(self.row.get(key))

        if len(matches) == 1:
            return matches[0]

        raise KeyError(f"Column '{column_name}' not found in row")

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

    def _lookup_value(self, row: Dict[str, Any], column: str) -> Any:
        if column in row:
            return row[column]

        if "." in column and column in row:
            return row[column]

        base_name = column.split(".")[-1]

        if base_name in row:
            return row[base_name]

        matches = [val for key, val in row.items() if key.endswith(f".{base_name}")]
        if len(matches) == 1:
            return matches[0]

        return None

    def get_aggregate(self, func_name: str, column: Optional[str] = None, distinct: bool = False) -> Any:
        func_name = func_name.upper()

        if func_name == "COUNT":
            if column is None:
                if distinct:
                    uniq = set()
                    for row in self.rows:
                        uniq.add(tuple(sorted(row.items())))
                    return len(uniq)
                return len(self.rows)

            values = []
            for row in self.rows:
                val = self._lookup_value(row, column)
                if val is not None:
                    values.append(val)

            if distinct:
                return len(set(values))
            return len(values)

        values = []
        for row in self.rows:
            val = self._lookup_value(row, column) if column is not None else None
            if val is not None:
                values.append(val)

        if distinct:
            values = list(dict.fromkeys(values))

        if func_name == "SUM":
            return sum(values) if values else 0
        elif func_name == "AVG":
            return sum(values) / len(values) if values else 0
        elif func_name == "MIN":
            return min(values) if values else None
        elif func_name == "MAX":
            return max(values) if values else None

        return None


class ExpressionEvaluator:
    def __init__(self, context: Optional[RowContext] = None, group_context: Optional[GroupContext] = None):
        self.context = context
        self.group_context = group_context

    def evaluate(self, node: ExprNode) -> Any:
        if node is None:
            return None

        if isinstance(node, NumNode):
            return node.num

        elif isinstance(node, StringNode):
            return node.value

        elif isinstance(node, BoolNode):
            return node.value

        elif isinstance(node, NullNode):
            return None

        elif isinstance(node, IdentNode):
            if self.context is not None:
                try:
                    return self.context.get_value(node.name)
                except KeyError:
                    pass

            if self.group_context is not None and self.group_context.rows:
                first_row = self.group_context.rows[0]
                if node.name in first_row:
                    return first_row[node.name]

                matches = [val for key, val in first_row.items() if key.endswith(f".{node.name}")]
                if len(matches) == 1:
                    return matches[0]

                return None

            if self.context is not None:
                return None

            raise RuntimeError(f"Cannot evaluate column '{node.name}' without context")

        elif isinstance(node, CompoundIdentNode):
            full_name = node.full_name
            last_name = node.parts[-1]

            if self.context is not None:
                try:
                    return self.context.get_value(full_name)
                except KeyError:
                    try:
                        return self.context.get_value(last_name)
                    except KeyError:
                        return None

            if self.group_context is not None and self.group_context.rows:
                first_row = self.group_context.rows[0]
                if full_name in first_row:
                    return first_row[full_name]
                if last_name in first_row:
                    return first_row[last_name]

                matches = [val for key, val in first_row.items() if key.endswith(f".{last_name}")]
                if len(matches) == 1:
                    return matches[0]

                return None

            raise RuntimeError("Cannot evaluate column without context")

        elif isinstance(node, UnOpNode):
            arg = self.evaluate(node.arg)
            return self._evaluate_unary(node.op, arg)

        elif isinstance(node, BinOpNode):
            left = self.evaluate(node.arg1)
            right = self.evaluate(node.arg2)
            return self._evaluate_binary(node.op, left, right)

        elif isinstance(node, BetweenNode):
            value = self.evaluate(node.expr)
            low = self.evaluate(node.low)
            high = self.evaluate(node.high)

            if value is None or low is None or high is None:
                result = False
            else:
                result = low <= value <= high

            return not result if node.negated else result

        elif isinstance(node, InNode):
            value = self.evaluate(node.expr)
            elements = [self.evaluate(el) for el in node.elements]

            if value is None:
                result = False
            else:
                result = value in elements

            return not result if node.negated else result

        elif isinstance(node, IsNullNode):
            value = self.evaluate(node.expr)
            result = value is None
            return not result if node.negated else result

        elif isinstance(node, ExistsNode):
            from SQL_compiler.executor.executor import QueryExecutor

            executor = QueryExecutor({})
            if self.context and self.context.table:
                executor.tables = {self.context.table.name: self.context.table}

            result = executor.execute(node.subquery)
            result_bool = len(result) > 0
            return not result_bool if node.negated else result_bool

        elif isinstance(node, SubQueryNode):
            from SQL_compiler.executor.executor import QueryExecutor

            executor = QueryExecutor({})
            if self.context and self.context.table:
                executor.tables = {self.context.table.name: self.context.table}

            result = executor.execute(node.query)
            return len(result) > 0

        elif isinstance(node, InSubqueryNode):
            value = self.evaluate(node.expr)

            from SQL_compiler.executor.executor import QueryExecutor

            executor = QueryExecutor({})
            if self.context and self.context.table:
                executor.tables = {self.context.table.name: self.context.table}

            subquery_result = executor.execute(node.subquery)
            values = []
            for row in subquery_result:
                if row:
                    values.append(next(iter(row.values())))

            result = value in values
            return not result if node.negated else result

        elif isinstance(node, FuncCallNode):
            if self.group_context is not None:
                column_name = None
                if node.args and isinstance(node.args[0], IdentNode):
                    column_name = node.args[0].name
                elif node.args and isinstance(node.args[0], CompoundIdentNode):
                    column_name = node.args[0].full_name
                elif node.args and isinstance(node.args[0], StarNode):
                    column_name = None

                return self.group_context.get_aggregate(
                    node.name.upper(),
                    column_name,
                    distinct=node.distinct,
                )

            if self.context is not None:
                if node.name.upper() == "COUNT":
                    return 1

            return None

        elif isinstance(node, StarNode):
            if self.context is None:
                return {}
            return {
                col: self.context.get_value(col)
                for col in self.context.table.column_names
            }

        else:
            raise NotImplementedError(f"Evaluation not implemented for {type(node)}")

    def _evaluate_unary(self, op: UnOp, arg: Any) -> Any:
        if op == UnOp.PLUS:
            return +self._to_number(arg)
        elif op == UnOp.MINUS:
            return -self._to_number(arg)
        elif op == UnOp.NOT:
            return not self._to_bool(arg)
        else:
            raise ValueError(f"Unknown unary operator: {op}")

    def _evaluate_binary(self, op: BinOp, left: Any, right: Any) -> Any:
        if op in (BinOp.ADD, BinOp.SUB, BinOp.MUL, BinOp.DIV, BinOp.REM):
            left_num = self._to_number(left)
            right_num = self._to_number(right)

            if op == BinOp.ADD:
                return left_num + right_num
            elif op == BinOp.SUB:
                return left_num - right_num
            elif op == BinOp.MUL:
                return left_num * right_num
            elif op == BinOp.DIV:
                if right_num == 0:
                    return None
                return left_num / right_num
            elif op == BinOp.REM:
                if right_num == 0:
                    return None
                return left_num % right_num

        elif op in (BinOp.EQ, BinOp.NE, BinOp.GT, BinOp.GE, BinOp.LT, BinOp.LE):
            if left is None or right is None:
                return False
            if op == BinOp.EQ:
                return left == right
            elif op == BinOp.NE:
                return left != right
            elif op == BinOp.GT:
                return left > right
            elif op == BinOp.GE:
                return left >= right
            elif op == BinOp.LT:
                return left < right
            elif op == BinOp.LE:
                return left <= right

        elif op in (BinOp.AND, BinOp.OR):
            left_bool = self._to_bool(left)
            if op == BinOp.AND:
                return left_bool and self._to_bool(right)
            elif op == BinOp.OR:
                return left_bool or self._to_bool(right)

        elif op in (BinOp.LIKE, BinOp.NOT_LIKE):
            if left is None or right is None:
                return False

            import re

            pattern = str(right)
            pattern = pattern.replace("%", ".*").replace("_", ".")
            pattern = f"^{pattern}$"

            try:
                match = bool(re.match(pattern, str(left), re.IGNORECASE))
                return not match if op == BinOp.NOT_LIKE else match
            except re.error:
                return False

        else:
            raise ValueError(f"Unknown binary operator: {op}")

    def _to_number(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _to_bool(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return bool(value) and value.lower() not in ("false", "0", "")
        return True
