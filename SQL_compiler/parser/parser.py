from pathlib import Path
from lark import Lark, Transformer
from SQL_compiler.parser.ast_nodes import *

grammar_path = Path(__file__).parent / 'parser.lark'
grammar = grammar_path.read_text(encoding='utf-8')
parser = Lark(grammar, start="start", parser="lalr")


class SQLASTBuilder(Transformer):
    """Построитель AST для SQL SELECT запросов"""

    def _is_node(self, obj):
        """Проверка, является ли объект узлом AST"""
        return isinstance(obj, AstNode)

    def _kw(self, obj) -> str:
        """Нормализация ключевых слов/токенов для сравнения"""
        try:
            # Token.type стабильно хранит имя терминала (SELECT/FROM/WHERE/...)
            if isinstance(obj, Token):
                return str(obj.type).upper()
        except Exception:
            pass
        return str(obj).upper()

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
        if len(args) == 1:
            return args[0]
        else:
            left = args[0]
            right = args[2]  # IDENT

            if isinstance(left, CompoundIdentNode):
                parts = left.parts + [right]
            elif isinstance(left, IdentNode):
                parts = [left.name, right]
            else:
                parts = [str(left), right]

            return CompoundIdentNode(parts)

    def ident(self, args):
        # ident: compound_ident | simple_ident
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
        """IS NULL expression: like_expr IS NOT? NULL"""
        if len(args) == 3:  # expr IS NULL
            return IsNullNode(args[0], negated=False)
        elif len(args) == 4:  # expr IS NOT NULL
            return IsNullNode(args[0], negated=True)
        else:
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
        """AND expression: between_expr (AND between_expr)*"""
        result = None
        for arg in args:
            if self._kw(arg) == 'AND':
                continue
            if result is None:
                result = arg
            else:
                result = BinOpNode(BinOp.AND, result, arg)

        return result if result is not None else (args[0] if args else None)

    def or_expr(self, args):
        """OR expression: and_expr (OR and_expr)*"""
        result = None
        for arg in args:
            if self._kw(arg) == 'OR':
                continue
            if result is None:
                result = arg
            else:
                result = BinOpNode(BinOp.OR, result, arg)
        return result if result is not None else (args[0] if args else None)

    def like(self, args):
        """LIKE expression: compare_expr NOT? LIKE compare_expr"""
        nodes = [a for a in args if isinstance(a, AstNode)]
        negated = any(self._kw(a) == 'NOT' for a in args)
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
        """IN expression: is_expr NOT? IN LPAREN (expr_list | select_stmt) RPAREN"""
        # args: [expr, 'IN', '(', elements, ')']
        # или [expr, 'NOT', 'IN', '(', elements, ')']

        expr = next((a for a in args if isinstance(a, AstNode)), None)
        negated = any(self._kw(a) == 'NOT' for a in args)
        elements = None
        for a in args:
            if isinstance(a, list):
                elements = a
            elif isinstance(a, SelectStmtNode):
                elements = a
        if elements is None:
            elements = args[3] if len(args) > 3 else []
        return InNode(expr, elements, negated=negated)

    def not_in(self, args):
        expr = args[0]
        elements = args[4] if isinstance(args[4], list) else [args[4]]
        return InNode(expr, elements, negated=True)

    def between(self, args):
        """BETWEEN expression: in_expr NOT? BETWEEN in_expr AND in_expr"""
        # args может быть: [expr, 'BETWEEN', low, 'AND', high]
        # или [expr, 'NOT', 'BETWEEN', low, 'AND', high]

        nodes = [a for a in args if isinstance(a, AstNode)]
        negated = any(self._kw(a) == 'NOT' for a in args)
        if len(nodes) >= 3:
            return BetweenNode(nodes[0], nodes[1], nodes[2], negated=negated)
        if len(args) == 5:
            return BetweenNode(args[0], args[2], args[4], negated=False)
        if len(args) == 6:
            return BetweenNode(args[0], args[3], args[5], negated=True)
        return BetweenNode(args[0], args[2], args[4], negated=False)

    def not_between(self, args):
        # args: [in_expr, NOT_BETWEEN, in_expr, AND, in_expr]
        return BetweenNode(args[0], args[2], args[4], negated=True)

    def not_between_tail(self, args):
        # Grammar: BETWEEN in_expr AND in_expr -> not_between_tail
        nodes = [a for a in args if isinstance(a, AstNode)]
        low = nodes[0] if len(nodes) > 0 else (args[1] if len(args) > 1 else None)
        high = nodes[1] if len(nodes) > 1 else (args[-1] if args else None)
        return ('NOT_BETWEEN', low, high)

    def not_like_tail(self, args):
        # Grammar: LIKE compare_expr -> not_like_tail
        right = next((a for a in args if isinstance(a, AstNode)), None)
        if right is None and len(args) >= 2:
            right = args[1]
        return ('NOT_LIKE', right)

    def not_in_tail(self, args):
        # Grammar: IN LPAREN expr_list RPAREN -> not_in_tail
        elements = None
        for a in args:
            if isinstance(a, list):
                elements = a
                break
        if elements is None:
            # fallback
            elements = args[0] if isinstance(args[0], list) else [args[0]]
        return ('NOT_IN', elements)

    def not_between_like(self, args):
        # Grammar: in_expr NOT not_between_like_tail -> not_between_like
        left = args[0]
        tail = args[2] if len(args) >= 3 else args[1]
        kind = tail[0]

        if kind == 'NOT_BETWEEN':
            _, low, high = tail
            return BetweenNode(left, low, high, negated=True)

        if kind == 'NOT_LIKE':
            _, right = tail
            return BinOpNode(BinOp.NOT_LIKE, left, right)

        if kind == 'NOT_IN':
            _, elements = tail
            return InNode(left, elements, negated=True)

        raise ValueError(f"Unknown NOT tail kind: {kind}")

    def expr_list(self, args):
        """Обработка списка выражений"""
        result = []
        for arg in args:
            if isinstance(arg, AstNode):
                result.append(arg)
            elif arg != ',':
                if isinstance(arg, AstNode):
                    result.append(arg)
        return result

    def exists_subquery(self, args):
        """EXISTS (subquery) or NOT EXISTS (subquery)"""
        # args: [EXISTS, LPAREN, select_stmt, RPAREN]
        # или [NOT, EXISTS, LPAREN, select_stmt, RPAREN]
        if len(args) == 4:  # EXISTS (subquery)
            return ExistsNode(args[2], negated=False)
        elif len(args) == 5:  # NOT EXISTS (subquery)
            return ExistsNode(args[3], negated=True)
        return SubQueryNode(args[2])

    def function_call(self, args):
        # args: [IDENT, LPAREN, ...args..., RPAREN]
        func_name = args[0]
        func_args = []

        for arg in args[2:-1]:
            if arg is None:
                continue
            if isinstance(arg, Token) and arg.type == 'STAR':
                func_args.append(StarNode())
            elif arg == '*':
                func_args.append(StarNode())
            elif hasattr(arg, 'tree'):
                func_args.append(arg)
            elif not isinstance(arg, str):
                func_args.append(arg)

        if not func_args and func_name.upper() == 'COUNT':
            func_args.append(StarNode())

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
        """Обработка списка выражений SELECT"""
        result = []
        for arg in args:
            if arg is None or arg == ',':
                continue
            if isinstance(arg, AstNode) or isinstance(arg, SelectItemNode):
                result.append(arg)
            elif isinstance(arg, list):
                result.extend(self.select_list(arg))
        return result

    def table_base(self, args):
        name = args[0]
        if isinstance(name, IdentNode):
            name = name.name
        # Grammar: ident (AS? ident)?
        # Возможные варианты args:
        # - [name]
        # - [name, alias]
        # - [name, 'AS', alias]
        alias = None
        if len(args) == 2:
            alias = args[1]
        elif len(args) >= 3:
            alias = args[2]
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
        # args: [table_primary, join_clause1, join_clause2, ...]
        result = [args[0]]
        for arg in args[1:]:
            if arg is not None:
                result.append(arg)
        return result

    def table_refs(self, args):
        # table_ref (COMMA table_ref)*
        tables = []
        for arg in args:
            if isinstance(arg, list):
                tables.extend(arg)
            elif arg is not None and arg != ',':
                tables.append(arg)
        return FromNode(tables)

    def join_clause(self, args):
        # join_type? JOIN table_primary (ON expr)?
        # Варианты:
        # 1. [JOIN, table_primary]
        # 2. [JOIN, table_primary, ON, expr]
        # 3. [join_type, JOIN, table_primary]
        # 4. [join_type, JOIN, table_primary, ON, expr]

        if len(args) == 2:  # JOIN table_primary
            join_type = 'JOIN'
            table = args[1]
            condition = None
        elif len(args) == 3:  # INNER JOIN table_primary
            join_type = args[0]
            table = args[2]
            condition = None
        elif len(args) == 4:  # JOIN table_primary ON expr
            join_type = 'JOIN'
            table = args[1]
            condition = args[3]
        elif len(args) == 5:  # INNER JOIN table_primary ON expr
            join_type = args[0]
            table = args[2]
            condition = args[4]
        else:
            join_type = 'JOIN'
            table = args[1] if len(args) > 1 else None
            condition = None

        return JoinNode(join_type, table, condition)

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
        expr = args[0]
        direction = self._kw(args[1]) if len(args) > 1 and self._kw(args[1]) in ('ASC', 'DESC') else 'ASC'
        return OrderingTermNode(expr, direction)

    def order_by(self, args):
        # ORDER BY ordering_term (COMMA ordering_term)*
        terms = []
        for arg in args[2:]:
            if isinstance(arg, OrderingTermNode):
                terms.append(arg)
        return terms

    def limit_offset(self, args):
        # LIMIT expr (OFFSET expr)?
        limit = args[1]
        offset = args[3] if len(args) > 3 else None
        return LimitOffsetNode(limit, offset)

    def where(self, args):
        """Обработка WHERE clause"""
        # args: [WHERE, expr]
        if len(args) >= 2:
            return args[1]  # возвращаем выражение
        return None

    def where_clause(self, args):
        """Обработка WHERE clause: WHERE expr"""
        if len(args) >= 2:
            return args[1]
        return None
    def where_expr(self, args):
        """Обработка WHERE выражения"""
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

        # SELECT
        if i < len(args) and self._kw(args[i]) == 'SELECT':
            i += 1

        # DISTINCT
        if i < len(args) and self._kw(args[i]) == 'DISTINCT':
            distinct = True
            i += 1

        # SELECT LIST
        if i < len(args) and isinstance(args[i], list):
            select_list = args[i]
            i += 1

        # Проходим по остальным аргументам
        while i < len(args):
            current = args[i]
            current_kw = self._kw(current)

            if current_kw == 'FROM':
                i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    from_node = args[i]
                    i += 1

            elif current_kw == 'WHERE':
                i += 1
                # Пропускаем None
                while i < len(args) and args[i] is None:
                    i += 1
                # Следующий аргумент - выражение WHERE
                # IMPORTANT: don't call hasattr(x,'tree') because property may raise if subtree contains None
                if i < len(args) and isinstance(args[i], AstNode):
                    where_clause = args[i]
                    i += 1

            elif current_kw == 'GROUP':
                i += 1
                if i < len(args) and self._kw(args[i]) == 'BY':
                    i += 1
                if i < len(args) and isinstance(args[i], list):
                    group_by = args[i]
                    i += 1

            elif current_kw == 'HAVING':
                i += 1
                while i < len(args) and args[i] is None:
                    i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    having_clause = args[i]
                    i += 1

            elif current_kw == 'ORDER':
                i += 1
                if i < len(args) and self._kw(args[i]) == 'BY':
                    i += 1
                # Собираем ordering_term через запятые, пока не начнется следующий clause.
                while i < len(args):
                    kw = self._kw(args[i])
                    if kw in ('LIMIT', 'GROUP', 'HAVING', 'WHERE', 'FROM', 'SELECT', 'ORDER', 'OFFSET'):
                        break
                    if isinstance(args[i], AstNode):
                        order_by.append(args[i])
                    i += 1

            elif current_kw == 'LIMIT':
                i += 1
                limit = None
                offset = None
                while i < len(args) and args[i] is None:
                    i += 1
                if i < len(args) and isinstance(args[i], AstNode):
                    limit = args[i]
                    i += 1
                if i < len(args) and self._kw(args[i]) == 'OFFSET':
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
            limit_offset=limit_offset
        )

    def _count_conditions(self, node):
        """Подсчет количества условий в AND узле"""
        if isinstance(node, BinOpNode) and node.op == BinOp.AND:
            return self._count_conditions(node.arg1) + self._count_conditions(node.arg2)
        return 1

    def __default__(self, data, children, meta):
        """Обработка неизвестных правил"""
        if len(children) == 1 and isinstance(children[0], AstNode):
            return children[0]
        elif len(children) == 1:
            return None
        # Фильтруем только AST узлы
        return [child for child in children if isinstance(child, AstNode)]


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
