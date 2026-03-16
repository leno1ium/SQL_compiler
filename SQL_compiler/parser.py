from pathlib import Path
from lark import Lark, Transformer
from ast_nodes import *

grammar_path = Path(__file__).parent / 'parser.lark'
grammar = grammar_path.read_text()
parser = Lark(grammar, start="start")


class ASTBuilder(Transformer):
    def num(self, args):
        return NumNode(args[0])

    def string(self, args):
        return StringNode(args[0])

    def bool(self, args):
        return BoolNode(args[0].lower() == 'true')

    def null_const(self, args):
        return NullNode()

    def compound_ident(self, args):
        return CompoundIdentNode([str(arg) for arg in args])

    def star(self, args):
        return StarNode()

    def exists_subquery(self, args):
        return SubQueryNode(args[0])

    def select_item(self, args):
        expr = args[0]
        alias = args[1] if len(args) > 1 else None
        return SelectItemNode(expr, alias)

    def select_all(self, args):
        return SelectItemNode(StarNode(), None)

    def select_list(self, args):
        return args

    def table_base(self, args):
        name = str(args[0])
        alias = args[1] if len(args) > 1 else None
        return TableBaseNode(name, alias)

    def table_subquery(self, args):
        query = args[0]
        alias = args[1] if len(args) > 1 else None
        return TableSubqueryNode(query, alias)

    def inner_join(self, args):
        return 'INNER JOIN'

    def left_join(self, args):
        return 'LEFT JOIN'

    def right_join(self, args):
        return 'RIGHT JOIN'

    def cross_join(self, args):
        return 'CROSS JOIN'

    def join_clause(self, args):
        if len(args) == 3:
            return JoinNode('JOIN', args[1], args[2])
        elif len(args) == 4:
            return JoinNode(args[0], args[2], args[3])
        return JoinNode('JOIN', args[1], None)

    def table_ref(self, args):
        return [args[0]] + list(args[1:])

    def table_refs(self, args):
        tables = []
        for arg in args:
            if isinstance(arg, list):
                tables.extend(arg)
            else:
                tables.append(arg)
        return tables

    def ordering_term(self, args):
        direction = args[1] if len(args) > 1 else 'ASC'
        return OrderingTermNode(args[0], direction)

    def order_by(self, args):
        return args[2:]

    def limit_offset(self, args):
        limit = args[1]
        offset = args[3] if len(args) > 3 else None
        return LimitOffsetNode(limit, offset)

    def get_un_op_node(self, name, *args):
        op_map = {
            'plus': UnOp.PLUS,
            'minus': UnOp.MINUS,
            'not_expr': UnOp.NOT
        }
        op = op_map.get(name, UnOp.PLUS)
        return UnOpNode(op, args[0])

    def get_bin_op_node(self, name, *args):
        op_map = {
            'mul': BinOp.MUL,
            'div': BinOp.DIV,
            'rem': BinOp.REM,
            'add': BinOp.ADD,
            'sub': BinOp.SUB,
            'gt': BinOp.GT,
            'ge': BinOp.GE,
            'lt': BinOp.LT,
            'le': BinOp.LE,
            'eq': BinOp.EQ,
            'ne': BinOp.NE,
            'and_expr': BinOp.AND,
            'or_expr': BinOp.OR,
            'like': BinOp.LIKE,
            'not_like': BinOp.NOT_LIKE,
            'in_expr': BinOp.IN,
            'not_in': BinOp.NOT_IN,
            'between': BinOp.BETWEEN,
            'not_between': BinOp.NOT_BETWEEN
        }

        if name in ('in_expr', 'not_in'):
            return InNode(args[0], args[1], negated=(name == 'not_in'))
        elif name in ('between', 'not_between'):
            return BetweenNode(args[0], args[1], args[2], negated=(name == 'not_between'))
        elif name in ('is_null', 'is_not_null'):
            return IsNullNode(args[0], negated=(name == 'is_not_null'))

        op = op_map.get(name)
        if op:
            return BinOpNode(op, args[0], args[1])

        raise ValueError(f"Unknown binary operator: {name}")

    def select_core(self, args):
        distinct = False
        i = 0

        if args[i] == 'SELECT':
            i += 1
        if i < len(args) and args[i] == 'DISTINCT':
            distinct = True
            i += 1

        select_list = args[i]
        i += 1

        from_tables = None
        where_clause = None

        while i < len(args):
            if args[i] == 'FROM':
                from_tables = args[i + 1]
                i += 2
            elif args[i] == 'WHERE':
                where_clause = args[i + 1]
                i += 2
            else:
                i += 1

        return SelectCoreNode(distinct, select_list, from_tables, where_clause, [], None)

    def select_stmt(self, args):
        core = args[0]
        order_by = None
        limit_offset = None

        for arg in args[1:]:
            if isinstance(arg, list):
                order_by = arg
            elif isinstance(arg, LimitOffsetNode):
                limit_offset = arg

        return SelectStmtNode(core, order_by or [], limit_offset)

    def __getattr__(self, item):

        if isinstance(item, str) and item.isupper():
            return lambda x: x  # Просто возвращаем строку

        if item in ('plus', 'minus', 'not_expr', 'is_null', 'is_not_null'):
            return lambda *args: self.get_un_op_node(item, *args)

        if item in ('mul', 'div', 'rem', 'add', 'sub',
                    'gt', 'ge', 'lt', 'le', 'eq', 'ne',
                    'and_expr', 'or_expr',
                    'like', 'not_like',
                    'in_expr', 'not_in',
                    'between', 'not_between'):
            return lambda *args: self.get_bin_op_node(item, *args)

        def create_node(*args):
            class_name = ''.join(part.capitalize() for part in item.split('_')) + 'Node'
            try:
                cls = globals()[class_name]
            except KeyError:
                from ast_nodes import globals as ast_globals
                cls = ast_globals().get(class_name)
                if not cls:
                    if len(args) == 1:
                        return args[0]
                    return args

            return cls(*args)

        return create_node


def parse(sql_query: str) -> SelectStmtNode:
    try:
        tree = parser.parse(sql_query)
        ast = ASTBuilder().transform(tree)
        return ast
    except Exception as e:
        raise Exception(f"SQL syntax error: {e}")


def print_ast(sql_query: str):
    ast = parse(sql_query)
    print("\nAST Tree:")
    for line in ast.tree:
        print(line)
