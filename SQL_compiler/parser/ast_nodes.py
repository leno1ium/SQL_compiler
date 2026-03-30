from abc import ABC, abstractmethod
from typing import Callable, Tuple, Optional, List
from enum import Enum


class AstNode(ABC):
    @property
    def childs(self) -> Tuple['AstNode', ...]:
        return ()

    @abstractmethod
    def __str__(self) -> str:
        pass

    @property
    def tree(self) -> List[str]:
        res = [str(self)]
        childs = self.childs
        for i, child in enumerate(childs):
            ch0, ch = '├', '│'
            if i == len(childs) - 1:
                ch0, ch = '└', ' '
            child_tree = child.tree
            for j, line in enumerate(child_tree):
                prefix = ch0 if j == 0 else ch
                res.append(prefix + ' ' + line)
        return res

    def visit(self, func: Callable[['AstNode'], None]) -> None:
        func(self)
        for child in self.childs:
            child.visit(func)

    def __getitem__(self, index):
        return self.childs[index] if index < len(self.childs) else None


class ExprNode(AstNode):  # expression
    pass


class ValueNode(ExprNode):  # literals
    pass


class StmtNode(AstNode):  # operators
    pass


# base values
class NumNode(ValueNode):
    def __init__(self, num: float):
        super().__init__()
        self.num = float(num)

    def __str__(self) -> str:
        return str(self.num)


class StringNode(ValueNode):
    def __init__(self, value: str):
        super().__init__()
        self.value = value.strip('"\'')

    def __str__(self) -> str:
        return f"'{self.value}'"


class BoolNode(ValueNode):
    def __init__(self, value: bool):
        super().__init__()
        self.value = value

    def __str__(self) -> str:
        return 'TRUE' if self.value else 'FALSE'


class NullNode(ValueNode):
    def __str__(self) -> str:
        return 'NULL'


# identifiers
class IdentNode(ExprNode):
    def __init__(self, name: str):
        super().__init__()
        self.name = str(name)

    def __str__(self) -> str:
        return self.name


class CompoundIdentNode(ExprNode):
    def __init__(self, parts: List[str]):
        super().__init__()
        self.parts = parts

    @property
    def full_name(self) -> str:
        return '.'.join(self.parts)

    @property
    def childs(self) -> Tuple['AstNode', ...]:
        return tuple(IdentNode(part) for part in self.parts)

    def __str__(self) -> str:
        return self.full_name


class StarNode(ExprNode):
    def __str__(self) -> str:
        return '*'


class FromNode(AstNode):
    def __init__(self, tables: List[AstNode]):
        super().__init__()
        self.tables = tables

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return tuple(self.tables)

    def __str__(self) -> str:
        return "FROM"


class OnNode(AstNode):
    def __init__(self, condition: ExprNode):
        super().__init__()
        self.condition = condition

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.condition,

    def __str__(self) -> str:
        return "ON"


# operators
class UnOp(Enum):
    NOT = 'NOT'
    PLUS = '+'
    MINUS = '-'


class UnOpNode(ExprNode):
    def __init__(self, op: UnOp, arg: ExprNode):
        super().__init__()
        self.op = op
        self.arg = arg

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.arg,

    def __str__(self) -> str:
        return str(self.op.value)


class BinOp(Enum):
    ADD = '+'
    SUB = '-'
    MUL = '*'
    DIV = '/'
    REM = '%'

    GT = '>'
    GE = '>='
    LT = '<'
    LE = '<='
    EQ = '=='
    NE = '!='
    NE2 = '<>'

    OR = 'OR'
    AND = 'AND'

    LIKE = 'LIKE'
    NOT_LIKE = 'NOT LIKE'
    IN = 'IN'
    NOT_IN = 'NOT IN'
    IS = 'IS'
    IS_NOT = 'IS NOT'


class BinOpNode(ExprNode):
    def __init__(self, op: BinOp, arg1: ExprNode, arg2: ExprNode):
        super().__init__()
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2

    @property
    def childs(self) -> Tuple[ExprNode, ExprNode]:
        return self.arg1, self.arg2

    def __str__(self) -> str:
        # Для логических операторов используем их названия
        if self.op in (BinOp.AND, BinOp.OR):
            return str(self.op.value)
        return str(self.op.value)


class BetweenNode(ExprNode):
    def __init__(self, expr: ExprNode, low: ExprNode, high: ExprNode, negated: bool = False):
        super().__init__()
        self.expr = expr
        self.low = low
        self.high = high
        self.negated = negated

    @property
    def childs(self) -> Tuple[ExprNode, ExprNode, ExprNode]:
        return self.expr, self.low, self.high

    def __str__(self) -> str:
        return 'NOT BETWEEN' if self.negated else 'BETWEEN'


class InNode(ExprNode):
    def __init__(self, expr: ExprNode, elements: List[ExprNode], negated: bool = False):
        super().__init__()
        self.expr = expr
        self.elements = elements
        self.negated = negated

    @property
    def childs(self) -> Tuple[ExprNode, ...]:
        return (self.expr,) + tuple(self.elements)

    def __str__(self) -> str:
        return 'NOT IN' if self.negated else 'IN'


class IsNullNode(ExprNode):
    def __init__(self, expr: ExprNode, negated: bool = False):
        super().__init__()
        self.expr = expr
        self.negated = negated

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.expr,

    def __str__(self) -> str:
        return 'IS NOT NULL' if self.negated else 'IS NULL'


# subqueries
class SubQueryNode(ExprNode):
    def __init__(self, query: 'SelectStmtNode'):
        super().__init__()
        self.query = query

    @property
    def childs(self) -> Tuple['SelectStmtNode', ...]:
        return self.query,

    def __str__(self) -> str:
        return 'EXISTS'


class ExistsNode(ExprNode):
    def __init__(self, subquery: 'SelectStmtNode', negated: bool = False):
        super().__init__()
        self.subquery = subquery
        self.negated = negated

    @property
    def childs(self) -> Tuple['SelectStmtNode']:
        return self.subquery,

    def __str__(self) -> str:
        return 'NOT EXISTS' if self.negated else 'EXISTS'


class InSubqueryNode(ExprNode):
    def __init__(self, expr: ExprNode, subquery: 'SelectStmtNode', negated: bool = False):
        super().__init__()
        self.expr = expr
        self.subquery = subquery
        self.negated = negated

    @property
    def childs(self) -> Tuple[ExprNode, 'SelectStmtNode']:
        return self.expr, self.subquery

    def __str__(self) -> str:
        return 'NOT IN' if self.negated else 'IN'


# select
class SelectItemNode(AstNode):
    def __init__(self, expr: ExprNode, alias: Optional[str] = None):
        super().__init__()
        self.expr = expr
        self.alias = alias

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.expr,

    def __str__(self):
        if self.alias:
            return f"{self.expr} AS {self.alias}"
        return str(self.expr)


class TableBaseNode(AstNode):
    def __init__(self, name: str, alias: Optional[str] = None):
        super().__init__()
        self.name = name
        self.alias = alias

    def __str__(self) -> str:
        if self.alias:
            return f"{self.name} AS {self.alias}"
        return self.name


class TableSubqueryNode(AstNode):
    def __init__(self, query: 'SelectStmtNode', alias: Optional[str] = None):
        super().__init__()
        self.query = query
        self.alias = alias

    @property
    def childs(self) -> Tuple['SelectStmtNode']:
        return self.query,

    def __str__(self) -> str:
        if self.alias:
            return f"(subquery) AS {self.alias}"
        return "(subquery)"


class JoinNode(AstNode):
    def __init__(self, join_type: str, table: AstNode, condition: Optional[ExprNode] = None):
        super().__init__()
        self.join_type = join_type.strip()  # Убираем лишние пробелы
        self.table = table
        self.condition = condition

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        children = [self.table]
        if self.condition:
            children.append(OnNode(self.condition))
        return tuple(children)

    def __str__(self) -> str:
        return self.join_type


class OrderingTermNode(AstNode):
    def __init__(self, expr: ExprNode, direction: str = 'ASC'):
        super().__init__()
        self.expr = expr
        self.direction = direction  # 'ASC' или 'DESC'

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.expr,

    def __str__(self) -> str:
        return f"{self.expr} {self.direction}"


class LimitOffsetNode(AstNode):
    def __init__(self, limit: ExprNode, offset: Optional[ExprNode] = None):
        super().__init__()
        self.limit = limit
        self.offset = offset

    @property
    def childs(self) -> Tuple[ExprNode, ...]:
        if self.offset:
            return self.limit, self.offset
        return self.limit,

    def __str__(self) -> str:
        result = f"LIMIT {self.limit}"
        if self.offset:
            result += f" OFFSET {self.offset}"
        return result


class SelectStmtNode(StmtNode):
    def __init__(self,
                 distinct: bool,
                 select_list: List[SelectItemNode],
                 from_node: Optional[FromNode] = None,
                 where_clause: Optional[AstNode] = None,
                 group_by: Optional[List[ExprNode]] = None,
                 having_clause: Optional[ExprNode] = None,
                 order_by: Optional[List[OrderingTermNode]] = None,
                 limit_offset: Optional[LimitOffsetNode] = None):
        super().__init__()
        self.distinct = distinct
        self.select_list = select_list
        self.from_node = from_node
        self.where_clause = where_clause
        self.group_by = group_by or []
        self.having_clause = having_clause
        self.order_by = order_by or []
        self.limit_offset = limit_offset

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        children = []

        # Добавляем SELECT список с заголовком
        if self.select_list:
            # Создаем специальный узел для SELECT списка
            children.append(SelectListNode(self.select_list))

        # Добавляем FROM
        if self.from_node:
            children.append(self.from_node)

        # Добавляем WHERE
        if self.where_clause is not None:
            # Проверяем, не обернут ли уже в WhereNode
            if not isinstance(self.where_clause, WhereNode):
                children.append(WhereNode(self.where_clause))
            else:
                children.append(self.where_clause)

        # Добавляем GROUP BY
        if self.group_by:
            children.append(GroupByNode(self.group_by))

        # Добавляем HAVING
        if self.having_clause:
            children.append(HavingNode(self.having_clause))

        # Добавляем ORDER BY
        if self.order_by:
            children.append(OrderByNode(self.order_by))

        # Добавляем LIMIT/OFFSET
        if self.limit_offset:
            children.append(self.limit_offset)

        return tuple(children)

    def __str__(self) -> str:
        base = 'SELECT'
        if self.distinct:
            base += ' DISTINCT'
        return base


class SelectListNode(AstNode):
    """Вспомогательный узел для отображения SELECT списка"""

    def __init__(self, select_list: List[SelectItemNode]):
        super().__init__()
        self.select_list = select_list

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return tuple(self.select_list)

    def __str__(self) -> str:
        return "SELECT"


class WhereNode(AstNode):
    """Узел для WHERE clause"""

    def __init__(self, condition: AstNode):
        super().__init__()
        self.condition = condition

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return self.condition,

    def __str__(self) -> str:
        return "WHERE"


class GroupByNode(AstNode):
    """Узел для GROUP BY clause"""

    def __init__(self, expressions: List[ExprNode]):
        super().__init__()
        self.expressions = expressions

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return tuple(self.expressions)

    def __str__(self) -> str:
        return "GROUP BY"


class HavingNode(AstNode):
    """Узел для HAVING clause"""

    def __init__(self, condition: AstNode):
        super().__init__()
        self.condition = condition

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return self.condition,

    def __str__(self) -> str:
        return "HAVING"


class OrderByNode(AstNode):
    """Узел для ORDER BY clause"""

    def __init__(self, terms: List[OrderingTermNode]):
        super().__init__()
        self.terms = terms

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return tuple(self.terms)

    def __str__(self) -> str:
        return "ORDER BY"


class StmtListNode(StmtNode):
    def __init__(self, *stmts: StmtNode):
        super().__init__()
        self.stmts = stmts

    @property
    def childs(self) -> Tuple[StmtNode, ...]:
        return self.stmts

    def __str__(self) -> str:
        return '...'


class FuncCallNode(ExprNode):
    """Вызов функции (COUNT, SUM, AVG, MIN, MAX)"""

    def __init__(self, name: str, args: List[ExprNode]):
        super().__init__()
        self.name = name
        self.args = args if args is not None else []

    @property
    def childs(self) -> Tuple[ExprNode, ...]:
        return tuple(self.args)

    def __str__(self) -> str:
        if len(self.args) == 1 and isinstance(self.args[0], StarNode):
            return f"{self.name}(*)"
        elif len(self.args) == 1:
            return f"{self.name}({self.args[0]})"
        elif len(self.args) == 0:
            return f"{self.name}()"
        else:
            args_str = ", ".join(str(arg) for arg in self.args if arg is not None)
            return f"{self.name}({args_str})"


class GroupByNode(AstNode):
    def __init__(self, expressions: List[ExprNode]):
        super().__init__()
        self.expressions = expressions

    @property
    def childs(self) -> Tuple[AstNode, ...]:
        return tuple(self.expressions)

    def __str__(self) -> str:
        return "GROUP BY"


class HavingNode(AstNode):
    def __init__(self, condition: ExprNode):
        super().__init__()
        self.condition = condition

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.condition,

    def __str__(self) -> str:
        return "HAVING"