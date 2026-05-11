from pathlib import Path
from lark import Lark, Transformer, Token

from SQL_compiler.parsing.ast_nodes import *

grammar_path = Path(__file__).parent / "parser.lark"
grammar = grammar_path.read_text(encoding="utf-8")
parser = Lark(grammar, start="start", parser="lalr")


class SQLASTBuilder(Transformer):
    """Построитель AST для SQL SELECT запросов"""

    def _is_node(self, obj):
        """Проверка, является ли объект узлом AST"""
        return isinstance(obj, AstNode)

    def _kw(self, obj) -> str:
        """Нормализация ключевых слов/токенов для сравнения"""
        try:
            if isinstance(obj, Token):
                return str(obj.type).upper()
        except Exception:
            pass
        return str(obj).upper()

    def _non_tokens(self, args):
        return [a for a in args if not isinstance(a, Token)]

    def num(self, args):
        return NumNode(args[0])

    def string(self, args):
        return StringNode(args[0])

    def bool(self, args):
        return BoolNode(args[0].lower() == "true")

    def null_const(self, args):
        return NullNode()

    def distinct(self, args):
        return args[0]

    def simple_ident(self, args):
        return IdentNode(args[0])

    def compound_ident(self, args):
        """Обработка составных идентификаторов"""
        if len(args) == 1:
            return args[0]
        left = args[0]
        right = args[2]

        if isinstance(left, CompoundIdentNode):
            parts = left.parts + [right]
        elif isinstance(left, IdentNode):
            parts = [left.name, right]
        else:
            parts = [str(left), right]

        return CompoundIdentNode(parts)

    def ident(self, args):
        return args[0]

    def plus(self, args):
        node = next((a for a in args if isinstance(a, AstNode)), args[0] if args else None)
        return UnOpNode(UnOp.PLUS, node)

    def minus(self, args):
        node = next((a for a in args if isinstance(a, AstNode)), args[0] if args else None)
        return UnOpNode(UnOp.MINUS, node)

    def not_expr(self, args):
        node = next((a for a in args if isinstance(a, AstNode)), None)
        if node is None and len(args) >= 2:
            node = args[1]
        return UnOpNode(UnOp.NOT, node)

    def is_null(self, args):
        if len(args) == 3:
            return IsNullNode(args[0], negated=False)
        elif len(args) == 4:
            return IsNullNode(args[0], negated=True)
        else:
            return IsNullNode(args[0], negated=False)

    def is_not_null(self, args):
        return IsNullNode(args[0], negated=True)

    def mul(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        left = nodes[0] if len(nodes) > 0 else args[0]
        right = nodes[1] if len(nodes) > 1 else (args[2] if len(args) > 2 else args[-1])
        return BinOpNode(BinOp.MUL, left, right)

    def div(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        left = nodes[0] if len(nodes) > 0 else args[0]
        right = nodes[1] if len(nodes) > 1 else (args[2] if len(args) > 2 else args[-1])
        return BinOpNode(BinOp.DIV, left, right)

    def rem(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        left = nodes[0] if len(nodes) > 0 else args[0]
        right = nodes[1] if len(nodes) > 1 else (args[2] if len(args) > 2 else args[-1])
        return BinOpNode(BinOp.REM, left, right)

    def add(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        left = nodes[0] if len(nodes) > 0 else args[0]
        right = nodes[1] if len(nodes) > 1 else (args[2] if len(args) > 2 else args[-1])
        return BinOpNode(BinOp.ADD, left, right)

    def sub(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        left = nodes[0] if len(nodes) > 0 else args[0]
        right = nodes[1] if len(nodes) > 1 else (args[2] if len(args) > 2 else args[-1])
        return BinOpNode(BinOp.SUB, left, right)

    def gt(self, args):
        return BinOpNode(BinOp.GT, args[0], args[1])

    def ge(self, args):
        return BinOpNode(BinOp.GE, args[0], args[1])

    def lt(self, args):
        return BinOpNode(BinOp.LT, args[0], args[1])

    def le(self, args):
        return BinOpNode(BinOp.LE, args[0], args[1])

    def eq(self, args):
        return BinOpNode(BinOp.EQ, args[0], args[1])

    def ne(self, args):
        return BinOpNode(BinOp.NE, args[0], args[1])

    def and_expr(self, args):
        result = None
        for arg in args:
            if self._kw(arg) == "AND":
                continue
            if result is None:
                result = arg
            else:
                result = BinOpNode(BinOp.AND, result, arg)
        return result if result is not None else (args[0] if args else None)

    def or_expr(self, args):
        result = None
        for arg in args:
            if self._kw(arg) == "OR":
                continue
            if result is None:
                result = arg
            else:
                result = BinOpNode(BinOp.OR, result, arg)
        return result if result is not None else (args[0] if args else None)

    def like(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        negated = any(self._kw(a) == "NOT" for a in args)
        if len(nodes) >= 2:
            left, right = nodes[0], nodes[1]
            op = BinOp.NOT_LIKE if negated else BinOp.LIKE
            return BinOpNode(op, left, right)
        if len(args) >= 3:
            return BinOpNode(BinOp.LIKE, args[0], args[2])
        return args[0] if args else None

    def not_like(self, args):
        return BinOpNode(BinOp.NOT_LIKE, args[0], args[1])

    def in_expr(self, args):
        expr = next(a for a in args if isinstance(a, AstNode))
        elements = next(a for a in args if isinstance(a, list))
        return InNode(expr, elements, negated=False)

    def not_in_expr(self, args):
        expr = args[0]
        elements = next(a for a in args if isinstance(a, list))
        return InNode(expr, elements, negated=True)

    def in_subquery(self, args):
        expr = args[0]
        subquery = next(a for a in args if isinstance(a, SelectStmtNode))
        return InSubqueryNode(expr, subquery, negated=False)

    def between(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        negated = any(self._kw(a) == "NOT" for a in args)
        if len(nodes) >= 3:
            return BetweenNode(nodes[0], nodes[1], nodes[2], negated=negated)
        if len(args) == 5:
            return BetweenNode(args[0], args[2], args[4], negated=False)
        if len(args) == 6:
            return BetweenNode(args[0], args[3], args[5], negated=True)
        return BetweenNode(args[0], args[2], args[4], negated=False)

    def not_like_tail(self, args):
        right = next(a for a in args if isinstance(a, AstNode))
        return ("NOT_LIKE", right)

    def not_between_tail(self, args):
        nodes = [a for a in args if isinstance(a, AstNode)]
        return ("NOT_BETWEEN", nodes[0], nodes[1])

    def not_in_tail(self, args):
        elements = next(a for a in args if isinstance(a, list))
        return ("NOT_IN", elements)

    def not_in_subquery(self, args):
        subquery = next(a for a in args if isinstance(a, SelectStmtNode))
        return ("NOT_IN_SUBQUERY", subquery)

    def not_between_like(self, args):
        left = None
        tail = None

        for a in args:
            if isinstance(a, AstNode) and left is None:
                left = a
            elif isinstance(a, tuple):
                tail = a

        if left is None or tail is None:
            raise ValueError(f"Invalid NOT expression args: {args}")

        kind = tail[0]

        if kind == "NOT_BETWEEN":
            _, low, high = tail
            return BetweenNode(left, low, high, negated=True)

        if kind == "NOT_LIKE":
            _, right = tail
            return BinOpNode(BinOp.NOT_LIKE, left, right)

        if kind == "NOT_IN":
            _, elements = tail
            return InNode(left, elements, negated=True)

        if kind == "NOT_IN_SUBQUERY":
            _, subquery = tail
            return InSubqueryNode(left, subquery, negated=True)

        raise ValueError(f"Unknown NOT tail kind: {kind}")

    def expr_list(self, args):
        result = []
        for arg in args:
            if isinstance(arg, AstNode):
                result.append(arg)
        return result

    def exists_subquery(self, args):
        if len(args) == 4:
            return ExistsNode(args[2], negated=False)
        elif len(args) == 5:
            return ExistsNode(args[3], negated=True)
        return SubQueryNode(args[2])

    def distinct_args(self, items):
        return DistinctArgsNode(items)

    def star_args(self, items):
        return StarNode()

    def expr_args(self, items):
        return items

    def function_call(self, items):
        filtered = [x for x in items if not isinstance(x, Token)]
        if not items:
            return FuncCallNode("", [])

        func_name = str(items[0]).upper()

        if not filtered:
            return FuncCallNode(func_name, [])

        arg = filtered[0]

        if isinstance(arg, StarNode):
            return FuncCallNode(func_name, [arg], distinct=False)

        if isinstance(arg, DistinctArgsNode):
            return FuncCallNode(func_name, arg.args, distinct=True)

        if isinstance(arg, list):
            return FuncCallNode(func_name, arg, distinct=False)

        if isinstance(arg, AstNode):
            return FuncCallNode(func_name, [arg], distinct=False)

        return FuncCallNode(func_name, [])

    def select_item(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]
        if len(filtered) == 1:
            return SelectItemNode(filtered[0], None)
        expr = filtered[0]
        alias = filtered[1] if len(filtered) > 1 else None
        if isinstance(alias, IdentNode):
            alias = alias.name
        return SelectItemNode(expr, alias)

    def select_all(self, args):
        return SelectItemNode(StarNode(), None)

    def select_list(self, args):
        result = []
        for arg in args:
            if arg is None or arg == ",":
                continue
            if isinstance(arg, AstNode) or isinstance(arg, SelectItemNode):
                result.append(arg)
            elif isinstance(arg, list):
                result.extend(self.select_list(arg))
        return result

    def table_base(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]
        if not filtered:
            return TableBaseNode("")

        name = filtered[0]
        if isinstance(name, IdentNode):
            name = name.name

        alias = None
        if len(filtered) == 2:
            alias = filtered[1]
        elif len(filtered) >= 3:
            alias = filtered[2]

        if isinstance(alias, IdentNode):
            alias = alias.name

        return TableBaseNode(str(name), alias)

    def table_subquery(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]
        query = filtered[0]
        alias = filtered[1] if len(filtered) > 1 else None
        if isinstance(alias, IdentNode):
            alias = alias.name
        return TableSubqueryNode(query, alias)

    def table_ref(self, args):
        base = args[0]
        joins = []
        for arg in args[1:]:
            if isinstance(arg, JoinNode):
                joins.append(arg)

        if hasattr(base, "joins"):
            base.joins.extend(joins)
        else:
            base.joins = joins

        return base

    def table_refs(self, args):
        tables = []
        for arg in args:
            if isinstance(arg, AstNode):
                tables.append(arg)
        return FromNode(tables)

    def join_clause(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]

        if len(filtered) == 2:
            if isinstance(filtered[0], str):
                join_type = filtered[0]
                table = filtered[1]
                condition = None
            else:
                join_type = "JOIN"
                table = filtered[0]
                condition = filtered[1]
        elif len(filtered) == 3:
            if isinstance(filtered[0], str):
                join_type = filtered[0]
                table = filtered[1]
                condition = filtered[2]
            else:
                join_type = "JOIN"
                table = filtered[0]
                condition = filtered[2]
        else:
            join_type = "JOIN"
            table = filtered[0] if filtered else None
            condition = filtered[1] if len(filtered) > 1 else None

        return JoinNode(join_type, table, condition)

    def inner_join(self, args):
        return "INNER JOIN"

    def left_join(self, args):
        if len(args) > 1 and args[1] == "OUTER":
            return "LEFT OUTER JOIN"
        return "LEFT JOIN"

    def right_join(self, args):
        if len(args) > 1 and args[1] == "OUTER":
            return "RIGHT OUTER JOIN"
        return "RIGHT JOIN"

    def cross_join(self, args):
        return "CROSS JOIN"

    def ordering_term(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]
        expr = filtered[0]
        direction = "ASC"
        # Проверяем наличие DESC в аргументах
        for arg in args:
            if self._kw(arg) == "DESC":
                direction = "DESC"
                break
            elif self._kw(arg) == "ASC":
                direction = "ASC"
        return OrderingTermNode(expr, direction)

    def order_by(self, args):
        terms = []
        for arg in args:
            if isinstance(arg, OrderingTermNode):
                terms.append(arg)
        return terms

    def limit_offset(self, args):
        filtered = [a for a in args if not isinstance(a, Token)]
        limit = filtered[0]
        offset = filtered[1] if len(filtered) > 1 else None
        return LimitOffsetNode(limit, offset)

    def where(self, args):
        if len(args) >= 2:
            return args[1]
        return None

    def where_clause(self, args):
        if len(args) >= 2:
            return args[1]
        return None

    def where_expr(self, args):
        return args[0] if args else None

    def select_stmt(self, args):
        distinct = False
        select_list = []
        from_node = None
        where_clause = None
        group_by = []
        having_clause = None
        order_by = []
        limit_offset = None

        i = 0

        if i < len(args) and self._kw(args[i]) == "SELECT":
            i += 1

        if i < len(args) and self._kw(args[i]) == "DISTINCT":
            distinct = True
            i += 1

        if i < len(args) and isinstance(args[i], list):
            select_list = args[i]
            i += 1

        while i < len(args):
            current = args[i]
            current_kw = self._kw(current)

            if current_kw == "FROM":
                i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    from_node = args[i]
                    i += 1

            elif current_kw == "WHERE":
                i += 1
                while i < len(args) and args[i] is None:
                    i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    where_clause = args[i]
                    i += 1

            elif current_kw == "GROUP":
                i += 1
                if i < len(args) and self._kw(args[i]) == "BY":
                    i += 1
                if i < len(args) and isinstance(args[i], list):
                    group_by = args[i]
                    i += 1

            elif current_kw == "HAVING":
                i += 1
                while i < len(args) and args[i] is None:
                    i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    having_clause = args[i]
                    i += 1

            elif current_kw == "ORDER":
                i += 1
                if i < len(args) and self._kw(args[i]) == "BY":
                    i += 1
                while i < len(args):
                    kw = self._kw(args[i])
                    if kw in ("LIMIT", "GROUP", "HAVING", "WHERE", "FROM", "SELECT", "ORDER", "OFFSET"):
                        break
                    if isinstance(args[i], AstNode):
                        order_by.append(args[i])
                    i += 1
                # Удаляем возможный None из order_by
                order_by = [o for o in order_by if o is not None]

            elif current_kw == "LIMIT":
                i += 1
                limit = None
                offset = None
                while i < len(args) and args[i] is None:
                    i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    limit = args[i]
                    i += 1
                if i < len(args) and self._kw(args[i]) == "OFFSET":
                    i += 1
                    while i < len(args) and args[i] is None:
                        i += 1
                    if i < len(args) and isinstance(args[i], AstNode):
                        offset = args[i]
                        i += 1
                if limit:
                    limit_offset = LimitOffsetNode(limit, offset)
            else:
                i += 1

        return SelectStmtNode(
            distinct=distinct,
            select_list=select_list,
            from_node=from_node,
            where_clause=where_clause,
            group_by=group_by,
            having_clause=having_clause,
            order_by=order_by,
            limit_offset=limit_offset,
        )

    def _count_conditions(self, node):
        if isinstance(node, BinOpNode) and node.op == BinOp.AND:
            return self._count_conditions(node.arg1) + self._count_conditions(node.arg2)
        return 1

    def __default__(self, data, children, meta):
        nodes = [c for c in children if isinstance(c, AstNode)]

        if len(nodes) == 1:
            return nodes[0]

        if nodes:
            return nodes

        return None


def parse(sql_query: str) -> SelectStmtNode:
    try:
        tree = parser.parse(sql_query)
        ast = SQLASTBuilder().transform(tree)
        return ast
    except Exception as e:
        raise Exception(f"SQL syntax error: {e}")


def print_ast(sql_query: str):
    try:
        ast = parse(sql_query)
        print("\nAST Tree:")
        for line in ast.tree:
            print(line)
    except Exception as e:
        print(f"Error: {e}")