from typing import Dict, Any
from SQL_compiler.executor.execution_context import RowContext, ExpressionEvaluator
from SQL_compiler.executor.table import Table
from SQL_compiler.parser.ast_nodes import *


class QueryExecutor:
    """
    Исполнитель SQL SELECT запросов.
    Принимает AST и выполняет его над загруженными таблицами.
    """

    def __init__(self, tables: Dict[str, Table]):
        self.tables = tables

    def execute(self, stmt: SelectStmtNode) -> List[Dict[str, Any]]:
        """
        Выполнить SELECT запрос

        Args:
            stmt: AST узлел SELECT запроса

        Returns:
            Список строк результата (каждая строка - словарь {колонка: значение})
        """
        if not isinstance(stmt, SelectStmtNode):
            raise TypeError(f"Expected SelectStmtNode, got {type(stmt)}")

        # Получаем таблицу из FROM секции
        table = self._get_table(stmt.core.from_node)
        if table is None:
            raise Exception(f"Table not found in query")

        print(f"\nВыполнение запроса над таблицей: {table.name}")

        # Применяем WHERE и собираем строки
        result_rows = []

        for row_idx, row in enumerate(table.rows):
            context = RowContext(table, row)
            context.row_index = row_idx

            if not self._check_where(stmt.core.where_clause, context):
                continue

            selected_row = self._project_row(stmt.core.select_list, context)
            result_rows.append(selected_row)

        print(f"Найдено строк: {len(result_rows)} из {len(table)}")

        if stmt.core.distinct:
            result_rows = self._apply_distinct(result_rows)
            print(f"После DISTINCT: {len(result_rows)} уникальных строк")

        if stmt.order_by:
            result_rows = self._apply_order_by(result_rows, stmt.order_by, table)
            print(f"Применена сортировка")

        if stmt.limit_offset:
            result_rows = self._apply_limit_offset(result_rows, stmt.limit_offset)
            print(f"Применены LIMIT/OFFSET")

        return result_rows

    def _get_table(self, from_node: Optional[FromNode]) -> Optional[Table]:
        """
        Получить таблицу из FROM узла

        Args:
            from_node: FROM узел AST

        Returns:
            Таблица или None
        """
        if from_node is None or not from_node.tables:
            return None

        # TODO: поддержка JOIN и подзапросов
        first_table = from_node.tables[0]

        if isinstance(first_table, TableBaseNode):
            table_name = first_table.name
            if table_name in self.tables:
                return self.tables[table_name]

        return None

    def _check_where(self, where_clause: Optional[ExprNode], context: RowContext) -> bool:
        """
        Проверить условие WHERE для строки

        Args:
            where_clause: Узел условия WHERE
            context: Контекст строки

        Returns:
            True если строка проходит условие
        """
        if where_clause is None:
            return True

        evaluator = ExpressionEvaluator(context)
        try:
            result = evaluator.evaluate(where_clause)
            return bool(result)
        except Exception as e:
            print(f"  Ошибка при вычислении WHERE: {e}")
            return False

    def _project_row(self, select_list: List[SelectItemNode], context: RowContext) -> Dict[str, Any]:
        """
        Выбрать нужные колонки из строки (SELECT)

        Args:
            select_list: Список элементов SELECT
            context: Контекст строки

        Returns:
            Словарь с выбранными колонками
        """
        result = {}
        evaluator = ExpressionEvaluator(context)

        for item in select_list:

            if isinstance(item.expr, StarNode):
                for col in context.table.column_names:
                    result[col] = context.get_value(col)
                continue

            try:
                value = evaluator.evaluate(item.expr)

                if item.alias:
                    name = item.alias
                elif isinstance(item.expr, IdentNode):
                    name = item.expr.name
                elif isinstance(item.expr, CompoundIdentNode):
                    name = item.expr.full_name
                else:
                    name = str(item.expr)

                result[name] = value

            except Exception as e:
                print(f"  Ошибка при вычислении выражения: {e}")
                name = item.alias or str(item.expr)
                result[name] = None

        return result

    def _apply_distinct(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Убрать дубликаты строк (DISTINCT)

        Args:
            rows: Исходные строки

        Returns:
            Уникальные строки
        """
        unique_rows = []
        seen = set()

        for row in rows:
            row_tuple = tuple(sorted(row.items()))
            if row_tuple not in seen:
                seen.add(row_tuple)
                unique_rows.append(row)

        return unique_rows

    def _apply_order_by(self, rows: List[Dict[str, Any]],
                        order_by: List[OrderingTermNode],
                        table: Table) -> List[Dict[str, Any]]:
        """
        Применить сортировку (ORDER BY)

        Args:
            rows: Исходные строки
            order_by: Список условий сортировки
            table: Таблица (для контекста)

        Returns:
            Отсортированные строки
        """

        def sort_key(row):
            context = RowContext(table, row)
            evaluator = ExpressionEvaluator(context)

            key = []
            for term in order_by:
                try:
                    value = evaluator.evaluate(term.expr)
                    key.append(value)
                except:
                    key.append(None)
            return tuple(key)

        reverse = any(term.direction == 'DESC' for term in order_by)

        try:
            return sorted(rows, key=sort_key, reverse=reverse)
        except Exception as e:
            print(f"  Ошибка при сортировке: {e}")
            return rows

    def _apply_limit_offset(self, rows: List[Dict[str, Any]],
                            limit_offset: LimitOffsetNode) -> List[Dict[str, Any]]:
        """
        Применить LIMIT и OFFSET

        Args:
            rows: Исходные строки
            limit_offset: Узел LIMIT/OFFSET

        Returns:
            Ограниченный набор строк
        """

        evaluator = ExpressionEvaluator(None)

        try:
            limit_val = evaluator.evaluate(limit_offset.limit)
            limit = int(limit_val) if limit_val is not None else len(rows)
        except:
            limit = len(rows)

        offset = 0
        if limit_offset.offset:
            try:
                offset_val = evaluator.evaluate(limit_offset.offset)
                offset = int(offset_val) if offset_val is not None else 0
            except:
                offset = 0

        start = min(offset, len(rows))
        end = min(start + limit, len(rows))

        return rows[start:end]