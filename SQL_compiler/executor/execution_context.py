from typing import Dict, Any, Optional, List
from SQL_compiler.executor.table import Table
from SQL_compiler.parser.ast_nodes import *


class RowContext:
    def __init__(self, table: Table, row: Dict[str, Any]):
        self.table = table
        self.row = row
        self.row_index = -1

    def get_value(self, column_name: str) -> Any:
        if column_name not in self.row:
            raise KeyError(f"Column '{column_name}' not found in row")
        return self.row.get(column_name)

    def get_type(self, column_name: str) -> type:
        return self.table.get_column_type(column_name)

    def has_column(self, column_name: str) -> bool:
        return column_name in self.row


class GroupContext:
    def __init__(self, table: Optional[Table], rows: List[Dict[str, Any]]):
        self.table = table
        self.rows = rows

    def get_aggregate(self, func_name: str, column: Optional[str] = None) -> Any:
        values = []
        for row in self.rows:
            if column:
                val = row.get(column)
            else:
                val = 1
            if val is not None:
                values.append(val)

        if func_name == 'COUNT':
            return len(values)
        elif func_name == 'SUM':
            return sum(values) if values else 0
        elif func_name == 'AVG':
            return sum(values) / len(values) if values else 0
        elif func_name == 'MIN':
            return min(values) if values else None
        elif func_name == 'MAX':
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
            if self.context is None:
                raise RuntimeError("Cannot evaluate column without context")
            return self.context.get_value(node.name)

        elif isinstance(node, CompoundIdentNode):
            if self.context is None:
                raise RuntimeError("Cannot evaluate column without context")
            return self.context.get_value(node.parts[-1])

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
            result = (value is None)
            return not result if node.negated else result

        elif isinstance(node, SubQueryNode):
            from SQL_compiler.executor.executor import QueryExecutor

            executor = QueryExecutor({})
            if self.context and self.context.table:
                executor.tables = {self.context.table.name: self.context.table}

            result = executor.execute(node.query)
            return len(result) > 0

        elif isinstance(node, FuncCallNode):
            if self.group_context is not None:
                column_name = node.args[0].name if node.args and hasattr(node.args[0], 'name') else None
                return self.group_context.get_aggregate(node.name.upper(), column_name)
            elif self.context is not None:
                if node.name.upper() in ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX'):
                    return 1 if node.name.upper() == 'COUNT' else None
            return None

        elif isinstance(node, StarNode):
            if self.context is None:
                return {}
            return {col: self.context.get_value(col)
                    for col in self.context.table.column_names}

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
            pattern = pattern.replace('%', '.*').replace('_', '.')
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
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
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
            return bool(value) and value.lower() not in ('false', '0', '')
        return True