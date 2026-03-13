from abc import ABC, abstractmethod
from typing import Callable, Tuple, Optional, List
from enum import Enum


class AstNode(ABC):
    @property
    def childs(self)->Tuple['AstNode', ...]:
        return ()

    @abstractmethod
    def __str__(self)->str:
        pass

    @property
    def tree(self)->[str, ...]:
        res = [str(self)]
        childs = self.childs
        for i, child in enumerate(childs):
            ch0, ch = '├', '│'
            if i == len(childs) - 1:
                ch0, ch = '└', ' '
            res.extend(((ch0 if j == 0 else ch) + ' ' + s for j, s in enumerate(child.tree)))
        return res

    def visit(self, func: Callable[['AstNode'], None])->None:
        func(self)
        map(func, self.childs)

    def __getitem__(self, index):
        return self.childs[index] if index < len(self.childs) else None


class ExprNode(AstNode):
    pass


class ValueNode(ExprNode):
    pass


class StmtNode(AstNode):
    pass


class NumNode(ValueNode):
    def __init__(self, num: float):
        super().__init__()
        self.num = float(num)

    def __str__(self)->str:
        return str(self.num)


class IdentNode(ExprNode):
    def __init__(self, name: str):
        super().__init__()
        self.name = str(name)

    def __str__(self)->str:
        return str(self.name)


class IncDecOp(Enum):
    PREFIX_INC = '++()'
    PREFIX_DEC = '--()'
    SUFFIX_INC = '()++'
    SUFFIX_DEC = '()--'


class IncDecNode(AstNode):
    def __init__(self, op: IncDecOp, ident: IdentNode):
        super().__init__()
        self.op = op
        self.ident = ident

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.ident,

    def __str__(self) -> str:
        return str(self.op.value)


class UnOp(Enum):
    NOT = '!'
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

    def __str__(self)->str:
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
    LOGIC_OR = '||'
    LOGIC_AND = '&&'


class BinOpNode(ExprNode):
    def __init__(self, op: BinOp, arg1: ExprNode, arg2: ExprNode):
        super().__init__()
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2

    @property
    def childs(self) -> Tuple[ExprNode, ExprNode]:
        return self.arg1, self.arg2

    def __str__(self)->str:
        return str(self.op.value)


class AssignNode(ExprNode, StmtNode):
    def __init__(self, var: ExprNode, val: ExprNode):
        super().__init__()
        self.var = var
        self.val = val

    @property
    def childs(self) -> Tuple[ExprNode, ExprNode]:
        return self.var, self.val

    def __str__(self)->str:
        return '='


class VarsDeclNode(StmtNode):
    def __init__(self, type: IdentNode, *vars: ExprNode):
        super().__init__()
        self.type = type
        self.vars = vars

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.vars

    def __str__(self) -> str:
        return str(self.type)


class CallNode(ExprNode, StmtNode):
    def __init__(self, name: IdentNode, *params: ExprNode):
        super().__init__()
        self.name = name
        self.params = params

    @property
    def childs(self) -> Tuple[ExprNode]:
        return self.params

    def __str__(self) -> str:
        return f'{self.name}()'


class IfNode(StmtNode):
    def __init__(self, cond: ExprNode, thenStmt: StmtNode, elseStmt: StmtNode = None):
        super().__init__()
        self.cond = cond
        self.thenStmt = thenStmt or StmtListNode()
        self.elseStmt = elseStmt

    @property
    def childs(self) -> Tuple[ExprNode, StmtNode, Optional[ExprNode]]:
        return self.cond, self.thenStmt, *([self.elseStmt] if self.elseStmt else [])

    def __str__(self) -> str:
        return 'if'


class WhileNode(StmtNode):
    def __init__(self, cond: ExprNode, body: StmtNode):
        super().__init__()
        self.cond = cond
        self.body = body or StmtListNode()

    @property
    def childs(self) -> Tuple[ExprNode, StmtNode]:
        return self.cond, self.body

    def __str__(self) -> str:
        return 'while'


class ForNode(StmtNode):
    def __init__(self, init: StmtNode, cond: ExprNode, next: StmtNode, body: StmtNode):
        super().__init__()
        self.init = init or StmtListNode()
        self.cond = cond or NumNode(1)
        self.next = next or StmtListNode()
        self.body = body or StmtListNode()

    @property
    def childs(self) -> Tuple[StmtNode, ExprNode, StmtNode, StmtNode]:
        return self.init, self.cond, self.next, self.body

    def __str__(self) -> str:
        return 'for'


class BreakNode(StmtNode):
    def __str__(self) -> str:
        return 'break'


class ContinueNode(StmtNode):
    def __str__(self) -> str:
        return 'continue'


class ReturnNode(StmtNode):
    def __init__(self, value: Optional[ExprNode] = None):
        super().__init__()
        self.value = value

    @property
    def childs(self) -> Tuple[ExprNode]:
        return (self.value,) if self.value else ()

    def __str__(self) -> str:
        return 'return'


class StmtListNode(StmtNode):
    def __init__(self, *stmts: StmtNode):
        super().__init__()
        self.stmts = stmts

    @property
    def childs(self) -> Tuple[StmtNode]:
        return self.stmts

    def __str__(self)->str:
        return '...'


class FuncNode(StmtNode):
    def __init__(self, type: IdentNode, name: IdentNode, params: List[VarsDeclNode],
                 body: StmtNode):
        super().__init__()
        self.type = type
        self.name = name
        self.params = params
        self.body = body

    @property
    def childs(self) -> Tuple[StmtNode]:
        return self.body,

    def __str__(self) -> str:
        params = ', '.join(f'{p.type} {p.vars[0]}' for p in self.params)
        return f'{self.type} {self.name}({params})'
