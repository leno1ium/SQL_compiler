from pathlib import Path

from lark import Lark, Transformer
from ast_nodes import *

grammar_path = Path(__file__).parent / 'parser.lark'
grammar = grammar_path.read_text()
parser = Lark(grammar, start="start")


class ASTBuilder(Transformer):

    def func(self, *args):
        return FuncNode(args[0], args[1], list(args[2:-1]), args[-1])

    def get_inc_dec_op_node(self, name, *args):
        op = IncDecOp[name.upper()]
        return IncDecNode(op, *args)

    def get_un_op_node(self, name, *args):
        op = UnOp[name.upper()]
        return UnOpNode(op, *args)

    def get_bin_op_node(self, name, *args):
        op = BinOp[name.upper()]
        return BinOpNode(op, *args)

    def __getattr__(self, item):
        if isinstance(item, str) and item.upper() == item:
            return lambda x: x

        if item in ('prefix_dec', 'prefix_inc', 'suffix_dec', 'suffix_inc'):
            return lambda *args: self.get_inc_dec_op_node(item, *args)

        if item in ('plus', 'minus', 'not'):
            return lambda *args: self.get_un_op_node(item, *args)

        if item in ('mul', 'div', 'rem',
                    'add', 'sub',
                    'gt', 'ge', 'lt', 'le',
                    'eq', 'ne',
                    'logic_and',
                    'logic_or'):
            return lambda *args: self.get_bin_op_node(item, *args)

        def get_node(*args):
            cls = eval(''.join(x.capitalize() or '_' for x in item.split('_')) + 'Node')
            return cls(*args)

        return get_node

    def _call_userfunc(self, tree, new_children=None):
        children = new_children if new_children is not None else tree.children
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree.data, children, tree.meta)
        else:
            return f(*children)


def parse(prog: str) -> StmtListNode:
    prog = parser.parse(str(prog))
    prog = ASTBuilder().transform(prog)
    return prog
