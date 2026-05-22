from pathlib import Path
from lark import Lark, Token, Transformer

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
        """Обработка составных идентификаторов с поддержкой внешних таблиц"""
        if len(args) == 1:
            return args[0]

        # Собираем все части, игнорируя точки как отдельные токены
        parts = []
        for arg in args:
            if isinstance(arg, str):
                parts.append(arg)
            elif isinstance(arg, IdentNode):
                parts.append(arg.name)
            elif isinstance(arg, Token):
                token_str = str(arg)
                if token_str != '.':
                    parts.append(token_str)

        # Объединяем части
        if len(parts) >= 2:
            return CompoundIdentNode(parts)

        return IdentNode(parts[0] if parts else "")

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
        if len(nodes) >= 2:
            left, right = nodes[0], nodes[1]
            return BinOpNode(BinOp.LIKE, left, right)
        if len(args) >= 3:
            return BinOpNode(BinOp.LIKE, args[0], args[2])
        return args[0] if args else None

    def between_expression(self, args):
        """Обработка BETWEEN выражения"""
        # args: [expr, NOT?, BETWEEN, low, AND, high]
        nodes = [a for a in args if isinstance(a, AstNode)]
        negated = False

        # Проверяем наличие NOT
        for arg in args:
            if isinstance(arg, Token) and self._kw(arg) == "NOT":
                negated = True
                break

        if len(nodes) >= 3:
            expr, low, high = nodes[0], nodes[1], nodes[2]
            return BetweenNode(expr, low, high, negated=negated)

        return None

    def in_expression(self, args):
        """Обработка IN выражения (объединенная для значений и подзапроса)"""
        # args: [expr, NOT?, IN, LPAREN, elements, RPAREN]
        expr = None
        negated = False
        elements_or_subquery = None

        for i, arg in enumerate(args):
            if isinstance(arg, AstNode) and expr is None:
                expr = arg
            elif isinstance(arg, Token) and self._kw(arg) == "NOT":
                negated = True
            elif isinstance(arg, (list, SelectStmtNode)):
                elements_or_subquery = arg

        if elements_or_subquery is None:
            return None

        # Если это подзапрос
        if isinstance(elements_or_subquery, SelectStmtNode):
            return InSubqueryNode(expr, elements_or_subquery, negated=negated)

        # Если это список значений
        if isinstance(elements_or_subquery, list):
            return InNode(expr, elements_or_subquery, negated=negated)

        return None

    def in_value_list(self, args):
        """Обработка списка значений для IN"""
        # args: [expr_list]
        return args[0] if args else []

    def in_subquery_stmt(self, args):
        """Обработка подзапроса для IN"""
        # args: [select_stmt]
        return args[0]

    def all_any_gt(self, args):
        """Обработка > ALL (subquery)"""
        return self._make_all_any(args, '>', 'ALL')

    def all_any_ge(self, args):
        """Обработка >= ALL (subquery)"""
        return self._make_all_any(args, '>=', 'ALL')

    def all_any_lt(self, args):
        """Обработка < ALL (subquery)"""
        return self._make_all_any(args, '<', 'ALL')

    def all_any_le(self, args):
        """Обработка <= ALL (subquery)"""
        return self._make_all_any(args, '<=', 'ALL')

    def all_any_eq(self, args):
        """Обработка = ALL (subquery)"""
        return self._make_all_any(args, '=', 'ALL')

    def all_any_ne(self, args):
        """Обработка != ALL (subquery)"""
        return self._make_all_any(args, '!=', 'ALL')

    def all_any_ne2(self, args):
        """Обработка <> ALL (subquery)"""
        return self._make_all_any(args, '<>', 'ALL')

    def any_gt(self, args):
        """Обработка > ANY (subquery)"""
        return self._make_all_any(args, '>', 'ANY')

    def any_ge(self, args):
        """Обработка >= ANY (subquery)"""
        return self._make_all_any(args, '>=', 'ANY')

    def any_lt(self, args):
        """Обработка < ANY (subquery)"""
        return self._make_all_any(args, '<', 'ANY')

    def any_le(self, args):
        """Обработка <= ANY (subquery)"""
        return self._make_all_any(args, '<=', 'ANY')

    def any_eq(self, args):
        """Обработка = ANY (subquery)"""
        return self._make_all_any(args, '=', 'ANY')

    def any_ne(self, args):
        """Обработка != ANY (subquery)"""
        return self._make_all_any(args, '!=', 'ANY')

    def any_ne2(self, args):
        """Обработка <> ANY (subquery)"""
        return self._make_all_any(args, '<>', 'ANY')

    def _make_all_any(self, args, operator: str, all_any_type: str):
        """Создание AllAnyNode из аргументов"""
        print(f"[DEBUG] _make_all_any: op={operator}, type={all_any_type}, args={args}")

        expr = None
        subquery = None

        for arg in args:
            if isinstance(arg, Token):
                # Skip tokens like LPAREN, RPAREN
                continue
            elif isinstance(arg, SelectStmtNode):
                subquery = arg
            elif isinstance(arg, AstNode) and expr is None:
                expr = arg

        print(f"[DEBUG] Created AllAnyNode: expr={expr}, op={operator}, type={all_any_type}")
        return AllAnyNode(expr, operator, subquery, all_any_type)

    def scalar_subquery(self, args):
        """Обработка скалярного подзапроса (SELECT ...) в выражении"""
        # args[0] - открывающая скобка, args[1] - select_stmt, args[2] - закрывающая скобка
        if len(args) >= 2:
            return ScalarSubqueryNode(args[1])
        return None

    def expr_list(self, args):
        """Обработка списка выражений"""
        result = []
        for arg in args:
            if isinstance(arg, list):
                result.extend(arg)
            elif isinstance(arg, AstNode):
                result.append(arg)
        return result

    def exists_subquery(self, args):
        if len(args) == 4:
            return ExistsNode(args[2], negated=False)
        elif len(args) == 5:
            return ExistsNode(args[3], negated=True)
        return None

    def distinct_args(self, items):
        return DistinctArgsNode(items)

    def star_args(self, items):
        return StarNode()

    def expr_args(self, items):
        return items

    def function_call(self, items):
        """Обработка вызова функции"""
        func_name = None
        args = []

        for i, item in enumerate(items):
            if isinstance(item, Token) and func_name is None:
                func_name = str(item).upper()
            elif isinstance(item, list):
                def extract_args(lst):
                    result = []
                    for x in lst:
                        if isinstance(x, list):
                            result.extend(extract_args(x))
                        elif isinstance(x, AstNode):
                            result.append(x)
                    return result

                args = extract_args(item)
            elif isinstance(item, AstNode):
                args.append(item)

        if func_name is None:
            func_name = "UNKNOWN"

        distinct = False
        for i, arg in enumerate(args):
            if isinstance(arg, DistinctArgsNode):
                distinct = True
                args = arg.args
                break

        return FuncCallNode(func_name, args, distinct=distinct)

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
            if isinstance(arg, (AstNode, SelectItemNode)):
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

    def concat_expr(self, args):
        """Обработка конкатенации строк ||"""
        nodes = [a for a in args if isinstance(a, AstNode)]
        if len(nodes) >= 2:
            left = nodes[-2]
            right = nodes[-1]
            return ConcatNode(left, right)
        return nodes[0] if nodes else None

    def union(self, args):
        """Обработка UNION"""
        left = None
        right = None
        all_flag = False

        for arg in args:
            if isinstance(arg, SelectStmtNode):
                if left is None:
                    left = arg
                else:
                    right = arg
            elif isinstance(arg, Token) and str(arg).upper() == "ALL":
                all_flag = True

        if left and right:
            return UnionNode(left, right, all_flag)
        return left or right

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

    def select_stmt(self, args):
        # Проверяем наличие UNION
        for i, arg in enumerate(args):
            if isinstance(arg, Token) and self._kw(arg) == "UNION":
                print(f"[DEBUG] Found UNION at position {i}")
                union_all = False

                if i + 1 < len(args) and isinstance(args[i + 1], Token) and self._kw(args[i + 1]) == "ALL":
                    union_all = True
                    right_start = i + 2
                    print(f"[DEBUG] UNION ALL detected")
                else:
                    right_start = i + 1

                # Левая часть - всё до UNION
                left_args = args[:i]
                # Правая часть - всё после UNION/UNION ALL
                right_args = args[right_start:]

                print(f"[DEBUG] Left args count: {len(left_args)}")
                print(f"[DEBUG] Right args count: {len(right_args)}")

                # Разбираем левую часть как обычный SELECT
                left_stmt = self._build_select_stmt(left_args)

                # Для правой части: если это уже SelectStmtNode, используем его
                # Иначе разбираем как SELECT
                if len(right_args) == 1 and isinstance(right_args[0], SelectStmtNode):
                    right_stmt = right_args[0]
                    print(f"[DEBUG] Right is already SelectStmtNode")
                else:
                    right_stmt = self._build_select_stmt(right_args)
                    print(f"[DEBUG] Built right from args")

                print(f"[DEBUG] Created UnionNode with all={union_all}")
                return UnionNode(left_stmt, right_stmt, union_all)

        # Нет UNION - обычный SELECT
        return self._build_select_stmt(args)

    def _build_select_stmt(self, args):
        """Построение SelectStmtNode из аргументов (без UNION)"""
        print(f"[DEBUG] Building SELECT from {len(args)} args")

        # Если args уже содержит SelectStmtNode, возвращаем его
        if len(args) == 1 and isinstance(args[0], SelectStmtNode):
            return args[0]

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
