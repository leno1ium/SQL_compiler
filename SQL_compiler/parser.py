from pathlib import Path
from lark import Lark, Transformer
from ast_nodes import *

grammar_path = Path(__file__).parent / 'parser.lark'
grammar = grammar_path.read_text(encoding='utf-8')
parser = Lark(grammar, start="start", parser="lalr")


class SQLASTBuilder(Transformer):
    """Построитель AST для SQL SELECT запросов"""

    # ============== БАЗОВЫЕ ТИПЫ ==============
    def num(self, args):
        return NumNode(args[0])

    def string(self, args):
        return StringNode(args[0])

    def bool(self, args):
        return BoolNode(args[0].lower() == 'true')

    def null_const(self, args):
        return NullNode()

    def distinct(self, args):
        return args[0]  # просто возвращаем DISTINCT

    # ============== ИДЕНТИФИКАТОРЫ ==============
    def simple_ident(self, args):
        return IdentNode(args[0])

    def compound_ident(self, args):
        # args может быть [simple_ident] или [compound_ident, DOT, IDENT]
        if len(args) == 1:
            # Это результат рекурсии
            return args[0]
        else:
            # Собираем составной идентификатор
            if isinstance(args[0], CompoundIdentNode):
                parts = args[0].parts + [args[2]]
            elif isinstance(args[0], IdentNode):
                parts = [args[0].name, args[2]]
            else:
                parts = [str(args[0]), str(args[2])]
            return CompoundIdentNode(parts)

    def ident(self, args):
        # ident: compound_ident | simple_ident
        return args[0]

    # ============== УНАРНЫЕ ОПЕРАТОРЫ ==============
    def plus(self, args):
        return UnOpNode(UnOp.PLUS, args[0])

    def minus(self, args):
        return UnOpNode(UnOp.MINUS, args[0])

    def not_expr(self, args):
        return UnOpNode(UnOp.NOT, args[0])

    def is_null(self, args):
        return IsNullNode(args[0], negated=False)

    def is_not_null(self, args):
        return IsNullNode(args[0], negated=True)

    # ============== БИНАРНЫЕ ОПЕРАТОРЫ ==============
    def mul(self, args):
        return BinOpNode(BinOp.MUL, args[0], args[1])

    def div(self, args):
        return BinOpNode(BinOp.DIV, args[0], args[1])

    def rem(self, args):
        return BinOpNode(BinOp.REM, args[0], args[1])

    def add(self, args):
        return BinOpNode(BinOp.ADD, args[0], args[1])

    def sub(self, args):
        return BinOpNode(BinOp.SUB, args[0], args[1])

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

    # ============== SQL ОПЕРАТОРЫ ==============
    def like(self, args):
        return BinOpNode(BinOp.LIKE, args[0], args[1])

    def not_like(self, args):
        return BinOpNode(BinOp.NOT_LIKE, args[0], args[1])

    def in_expr(self, args):
        # args: [like_expr, IN, LPAREN, elements..., RPAREN]
        expr = args[0]
        elements = [arg for arg in args[3:-1] if not isinstance(arg, str)]
        return InNode(expr, elements, negated=False)

    def not_in(self, args):
        expr = args[0]
        elements = [arg for arg in args[4:-1] if not isinstance(arg, str)]
        return InNode(expr, elements, negated=True)

    def between(self, args):
        # args: [in_expr, BETWEEN, in_expr, AND, in_expr]
        return BetweenNode(args[0], args[2], args[4], negated=False)

    def not_between(self, args):
        return BetweenNode(args[0], args[3], args[5], negated=True)

    def exists_subquery(self, args):
        return SubQueryNode(args[2])  # EXISTS LPAREN select_stmt RPAREN

    # ============== SELECT КОНСТРУКЦИИ ==============
    def select_item(self, args):
        if len(args) == 1:
            return SelectItemNode(args[0], None)
        else:
            # expr AS? ident
            expr = args[0]
            alias = args[2] if len(args) > 2 else args[1]
            if isinstance(alias, IdentNode):
                alias = alias.name
            return SelectItemNode(expr, alias)

    def select_all(self, args):
        return SelectItemNode(StarNode(), None)

    def select_list(self, args):
        return [arg for arg in args if not isinstance(arg, str)]

    def table_base(self, args):
        name = args[0]
        if isinstance(name, IdentNode):
            name = name.name
        alias = args[2] if len(args) > 2 else None
        if isinstance(alias, IdentNode):
            alias = alias.name
        return TableBaseNode(str(name), alias)

    def table_subquery(self, args):
        query = args[1]  # LPAREN select_stmt RPAREN
        alias = args[3] if len(args) > 3 else None
        if isinstance(alias, IdentNode):
            alias = alias.name
        return TableSubqueryNode(query, alias)

    def table_ref(self, args):
        # table_primary (join_clause)*
        return [args[0]] + list(args[1:])

    def table_refs(self, args):
        tables = []
        for arg in args:
            if isinstance(arg, list):
                tables.extend(arg)
            else:
                tables.append(arg)
        return tables

    def join_clause(self, args):
        # join_type? JOIN table_primary (ON expr)?
        if len(args) == 3:  # JOIN table_primary
            return JoinNode('JOIN', args[1], None)
        elif len(args) == 4:  # JOIN table_primary ON expr
            return JoinNode('JOIN', args[1], args[3])
        elif len(args) == 5:  # INNER JOIN table_primary ON expr
            return JoinNode(args[0], args[2], args[4])
        else:  # INNER JOIN table_primary
            return JoinNode(args[0], args[2], None)

    def inner_join(self, args):
        return 'INNER JOIN'

    def left_join(self, args):
        if len(args) > 1 and args[1] == 'OUTER':
            return 'LEFT OUTER JOIN'
        return 'LEFT JOIN'

    def right_join(self, args):
        if len(args) > 1 and args[1] == 'OUTER':
            return 'RIGHT OUTER JOIN'
        return 'RIGHT JOIN'

    def cross_join(self, args):
        return 'CROSS JOIN'

    def select_core(self, args):
        distinct = False
        i = 0

        # SELECT
        if args[i] == 'SELECT':
            i += 1

        # DISTINCT?
        if i < len(args) and args[i] == 'DISTINCT':
            distinct = True
            i += 1

        # select_list
        select_list = args[i]
        i += 1

        from_tables = None
        where_clause = None
        group_by = []
        having_clause = None

        while i < len(args):
            if args[i] == 'FROM':
                from_tables = args[i + 1]
                i += 2
            elif args[i] == 'WHERE':
                where_clause = args[i + 1]
                i += 2
            elif args[i] == 'GROUP':
                # GROUP BY expr (COMMA expr)*
                i += 2  # пропускаем GROUP и BY
                group_by = []
                while i < len(args) and args[i] != 'HAVING':
                    if not isinstance(args[i], str):
                        group_by.append(args[i])
                    i += 1
            elif args[i] == 'HAVING':
                having_clause = args[i + 1]
                i += 2
            else:
                i += 1

        return SelectCoreNode(distinct, select_list, from_tables,
                              where_clause, group_by, having_clause)

    def ordering_term(self, args):
        expr = args[0]
        direction = args[1] if len(args) > 1 else 'ASC'
        return OrderingTermNode(expr, direction)

    def order_by(self, args):
        # ORDER BY ordering_term (COMMA ordering_term)*
        terms = []
        for arg in args[2:]:  # пропускаем ORDER и BY
            if isinstance(arg, OrderingTermNode):
                terms.append(arg)
        return terms

    def limit_offset(self, args):
        # LIMIT expr (OFFSET expr)?
        limit = args[1]
        offset = args[3] if len(args) > 3 else None
        return LimitOffsetNode(limit, offset)

    def select_stmt(self, args):
        core = args[0]
        order_by = None
        limit_offset = None

        for arg in args[1:]:
            if isinstance(arg, list) and arg and isinstance(arg[0], OrderingTermNode):
                order_by = arg
            elif isinstance(arg, LimitOffsetNode):
                limit_offset = arg

        return SelectStmtNode(core, order_by or [], limit_offset)

    # ============== ВСПОМОГАТЕЛЬНЫЕ ==============
    def __default__(self, data, children, meta):
        """Обработка неизвестных правил (терминалы)"""
        if len(children) == 1:
            return children[0]
        return children


def parse(sql_query: str) -> SelectStmtNode:
    """Парсинг SQL запроса в AST"""
    try:
        tree = parser.parse(sql_query)
        ast = SQLASTBuilder().transform(tree)
        return ast
    except Exception as e:
        raise Exception(f"SQL syntax error: {e}")


def print_ast(sql_query: str):
    """Парсинг и вывод AST в виде дерева"""
    try:
        ast = parse(sql_query)
        print("\nAST Tree:")
        for line in ast.tree:
            print(line)
    except Exception as e:
        print(f"Error: {e}")