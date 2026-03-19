from pathlib import Path
from lark import Lark, Transformer
from ast_nodes import *

grammar_path = Path(__file__).parent / 'parser.lark'
grammar = grammar_path.read_text(encoding='utf-8')
parser = Lark(grammar, start="start", parser="lalr")


class SQLASTBuilder(Transformer):
    """Построитель AST для SQL SELECT запросов"""

    def _is_node(self, obj):
        """Проверка, является ли объект узлом AST"""
        return hasattr(obj, 'tree')

    def num(self, args):
        return NumNode(args[0])

    def string(self, args):
        return StringNode(args[0])

    def bool(self, args):
        return BoolNode(args[0].lower() == 'true')

    def null_const(self, args):
        return NullNode()

    def distinct(self, args):
        return args[0]

    def simple_ident(self, args):
        return IdentNode(args[0])

    def compound_ident(self, args):
        """Обработка составных идентификаторов"""
        # args может быть: [simple_ident] или [compound_ident, DOT, IDENT]
        if len(args) == 1:
            return args[0]
        else:
            # Получаем левую часть (может быть IdentNode или CompoundIdentNode)
            left = args[0]
            right = args[2]  # IDENT

            if isinstance(left, CompoundIdentNode):
                parts = left.parts + [right]
            elif isinstance(left, IdentNode):
                parts = [left.name, right]
            else:
                # Если left - это строка или Token
                parts = [str(left), right]

            return CompoundIdentNode(parts)

    def ident(self, args):
        # ident: compound_ident | simple_ident
        return args[0]

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

    def and_expr(self, args):
        """AND оператор - обрабатывает цепочки AND"""
        if len(args) == 1:
            return args[0]
        # Ищем все части с AND
        result = args[0]
        i = 1
        while i < len(args):
            if args[i] == 'AND':
                result = BinOpNode(BinOp.AND, result, args[i + 1])
                i += 2
            else:
                i += 1
        return result

    def or_expr(self, args):
        """OR оператор - обрабатывает цепочки OR"""
        if len(args) == 1:
            return args[0]
        # Ищем все части с OR
        result = args[0]
        i = 1
        while i < len(args):
            if args[i] == 'OR':
                result = BinOpNode(BinOp.OR, result, args[i + 1])
                i += 2
            else:
                i += 1
        return result

    def like(self, args):
        return BinOpNode(BinOp.LIKE, args[0], args[1])

    def not_like(self, args):
        return BinOpNode(BinOp.NOT_LIKE, args[0], args[1])

    def in_expr(self, args):
        """Обработка IN выражения"""
        # args: [is_expr, IN, LPAREN, expr_list, RPAREN] или [is_expr, NOT, IN, LPAREN, expr_list, RPAREN]
        if args[1] == 'NOT':
            expr = args[0]
            elements = args[4] if isinstance(args[4], list) else [args[4]]
            return InNode(expr, elements, negated=True)
        else:
            expr = args[0]
            elements = args[3] if isinstance(args[3], list) else [args[3]]
            return InNode(expr, elements, negated=False)

    def not_in(self, args):
        """Обработка NOT IN выражения (альтернативный вариант)"""
        expr = args[0]
        elements = args[4] if isinstance(args[4], list) else [args[4]]
        return InNode(expr, elements, negated=True)

    def between(self, args):
        """Обработка BETWEEN выражения"""
        # args: [in_expr, BETWEEN, in_expr, AND, in_expr]
        return BetweenNode(args[0], args[2], args[4], negated=False)

    def not_between(self, args):
        """Обработка NOT BETWEEN выражения"""
        # args: [in_expr, NOT, BETWEEN, in_expr, AND, in_expr]
        return BetweenNode(args[0], args[3], args[5], negated=True)

    def expr_list(self, args):
        """Обработка списка выражений"""
        result = []
        for arg in args:
            if hasattr(arg, 'tree'):
                result.append(arg)
            elif arg != ',':
                # Может быть выражение без запятой
                if hasattr(arg, 'tree'):
                    result.append(arg)
        return result

    def exists_subquery(self, args):
        return SubQueryNode(args[2])  # EXISTS LPAREN select_stmt RPAREN

    def function_call(self, args):
        """Вызов функции: COUNT(*), SUM(price), etc."""
        # args: [IDENT, LPAREN, ...args..., RPAREN]
        func_name = args[0]
        func_args = []

        # Собираем аргументы между LPAREN и RPAREN
        for arg in args[2:-1]:  # пропускаем IDENT, LPAREN и последний RPAREN
            if not isinstance(arg, str) and not hasattr(arg, 'type'):
                func_args.append(arg)

        return FuncCallNode(func_name, func_args)

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
        """Список элементов SELECT"""
        result = []
        for arg in args:
            if self._is_node(arg):
                result.append(arg)
        return result

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
        return FromNode(tables)

    def join_clause(self, args):
        # join_type? JOIN table_primary (ON expr)?
        if len(args) == 3:  # JOIN table_primary
            return JoinNode('JOIN', args[1], None)
        elif len(args) == 4:  # JOIN table_primary ON expr
            on_node = OnNode(args[3])
            return JoinNode('JOIN', args[1], on_node)
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

    def ordering_term(self, args):
        """Термин сортировки: expr (ASC | DESC)?"""
        expr = args[0]
        direction = args[1] if len(args) > 1 and args[1] in ('ASC', 'DESC') else 'ASC'
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
        """Единый узел для всего SELECT запроса"""
        distinct = False
        select_list = None
        from_node = None
        where_clause = None
        group_by = []
        having_clause = None
        order_by = []
        limit_offset = None

        i = 0

        # SELECT
        if args[i] == 'SELECT':
            i += 1

        # DISTINCT?
        if i < len(args) and args[i] == 'DISTINCT':
            distinct = True
            i += 1

        # select_list
        if i < len(args) and isinstance(args[i], list):
            select_list = args[i]
        i += 1

        while i < len(args):
            current = args[i]

            if isinstance(current, str):
                if current == 'FROM':
                    if i + 1 < len(args) and hasattr(args[i + 1], 'tree'):
                        from_node = args[i + 1]
                    i += 2
                elif current == 'WHERE':
                    if i + 1 < len(args) and hasattr(args[i + 1], 'tree'):
                        where_clause = args[i + 1]
                    i += 2
                elif current == 'GROUP':
                    i += 2  # пропускаем GROUP и BY
                    if i < len(args) and isinstance(args[i], list):
                        group_by = args[i]
                        i += 1
                    else:
                        while i < len(args) and not isinstance(args[i], str):
                            if hasattr(args[i], 'tree'):
                                group_by.append(args[i])
                            i += 1
                elif current == 'HAVING':
                    if i + 1 < len(args) and hasattr(args[i + 1], 'tree'):
                        having_clause = args[i + 1]
                    i += 2
                elif current == 'ORDER':
                    i += 2  # пропускаем ORDER и BY
                    # Собираем термины ORDER BY
                    while i < len(args) and not isinstance(args[i], str):
                        if hasattr(args[i], 'tree'):
                            order_by.append(args[i])
                        i += 1
                elif current == 'LIMIT':
                    limit = None
                    offset = None

                    if i + 1 < len(args) and hasattr(args[i + 1], 'tree'):
                        limit = args[i + 1]

                    if i + 2 < len(args) and args[i + 2] == 'OFFSET':
                        if i + 3 < len(args) and hasattr(args[i + 3], 'tree'):
                            offset = args[i + 3]
                        i += 4
                    else:
                        i += 2

                    if limit:
                        limit_offset = LimitOffsetNode(limit, offset)
                else:
                    i += 1
            else:
                i += 1

        # Создаем узел SELECT
        return SelectStmtNode(
            distinct=distinct,
            select_list=select_list if isinstance(select_list, list) else [],
            from_node=from_node,
            where_clause=where_clause,
            group_by=group_by,
            having_clause=having_clause,
            order_by=order_by,
            limit_offset=limit_offset
        )

    def __default__(self, data, children, meta):
        """Обработка неизвестных правил"""
        if len(children) == 1 and hasattr(children[0], 'tree'):
            return children[0]
        elif len(children) == 1:
            return None
        # Фильтруем только AST узлы
        return [child for child in children if hasattr(child, 'tree')]


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
