from typing import List, Dict, Any, Optional, Tuple
from SQL_compiler.executor.table import Table
from SQL_compiler.executor.execution_context import RowContext, ExpressionEvaluator, GroupContext
from SQL_compiler.parser.ast_nodes import *


class QueryExecutor:
    def __init__(self, tables: Dict[str, Table]):
        self.tables = tables

    def execute(self, stmt: SelectStmtNode) -> List[Dict[str, Any]]:
        if not isinstance(stmt, SelectStmtNode):
            raise TypeError(f"Expected SelectStmtNode, got {type(stmt)}")

        if stmt.from_node is None or not stmt.from_node.tables:
            return self._execute_without_from(stmt)

        result_rows = self._execute_from_and_joins(stmt.from_node, stmt.where_clause)

        if stmt.group_by:
            result_rows = self._execute_group_by(result_rows, stmt.group_by, stmt.select_list, stmt.having_clause)
        else:
            result_rows = self._execute_select(result_rows, stmt.select_list)

        if stmt.distinct:
            result_rows = self._apply_distinct(result_rows)
            print(f"После DISTINCT: {len(result_rows)} уникальных строк")

        if stmt.order_by:
            result_rows = self._apply_order_by(result_rows, stmt.order_by)

        if stmt.limit_offset:
            result_rows = self._apply_limit_offset(result_rows, stmt.limit_offset)

        return result_rows

    def _execute_without_from(self, stmt: SelectStmtNode) -> List[Dict[str, Any]]:
        result = []
        evaluator = ExpressionEvaluator(None)
        for item in stmt.select_list:
            try:
                value = evaluator.evaluate(item.expr)
                name = item.alias or str(item.expr)
                result.append({name: value})
            except Exception as e:
                print(f"Ошибка: {e}")
        return result

    def _execute_from_and_joins(self, from_node: FromNode, where_clause: Optional[ExprNode]) -> List[Dict[str, Any]]:
        if not from_node.tables:
            return []

        current_rows = None

        for table_node in from_node.tables:
            if isinstance(table_node, TableBaseNode):
                table = self.tables.get(table_node.name)
                if table is None:
                    continue

                if current_rows is None:
                    current_rows = [row.copy() for row in table.rows]
                else:
                    new_rows = []
                    for existing_row in current_rows:
                        for new_row in table.rows:
                            merged = existing_row.copy()
                            for key, value in new_row.items():
                                merged[key] = value
                            new_rows.append(merged)
                    current_rows = new_rows

            elif isinstance(table_node, JoinNode):
                right_table = self._get_table_from_node(table_node.table)
                if right_table is None:
                    continue

                condition = None
                if table_node.condition:
                    if isinstance(table_node.condition, OnNode):
                        condition = table_node.condition.condition
                    else:
                        condition = table_node.condition

                join_type = table_node.join_type

                new_rows = []
                for existing_row in current_rows:
                    matched = False
                    for right_row in right_table.rows:
                        merged = existing_row.copy()
                        for key, value in right_row.items():
                            merged[key] = value

                        if condition:
                            temp_table = self._create_temp_table(merged)
                            context = RowContext(temp_table, merged)
                            evaluator = ExpressionEvaluator(context)
                            try:
                                if not bool(evaluator.evaluate(condition)):
                                    continue
                            except Exception:
                                continue

                        matched = True
                        new_rows.append(merged)

                    if join_type in ('LEFT JOIN', 'LEFT OUTER JOIN') and not matched:
                        merged = existing_row.copy()
                        for col in right_table.column_names:
                            merged[col] = None
                        new_rows.append(merged)

                current_rows = new_rows

        if where_clause and current_rows:
            filtered_rows = []
            for row in current_rows:
                temp_table = self._create_temp_table(row)
                context = RowContext(temp_table, row)
                evaluator = ExpressionEvaluator(context)
                try:
                    if bool(evaluator.evaluate(where_clause)):
                        filtered_rows.append(row)
                except Exception:
                    continue
            current_rows = filtered_rows

        return current_rows if current_rows else []

    def _get_table_from_node(self, node: AstNode) -> Optional[Table]:
        if isinstance(node, TableBaseNode):
            return self.tables.get(node.name)
        elif isinstance(node, TableSubqueryNode):
            sub_executor = QueryExecutor(self.tables)
            sub_result = sub_executor.execute(node.query)
            if sub_result:
                return self._dict_to_table(f"_subquery", sub_result)
        return None

    def _create_temp_table(self, row: Dict[str, Any]) -> Table:
        table = Table("temp")
        for col, value in row.items():
            col_type = type(value) if value is not None else str
            table.add_column(col, col_type)
        table.add_row(row)
        return table

    def _dict_to_table(self, name: str, rows: List[Dict[str, Any]]) -> Table:
        table = Table(name)
        if not rows:
            return table
        for col in rows[0].keys():
            col_type = type(rows[0][col]) if rows[0][col] is not None else str
            table.add_column(col, col_type)
        for row in rows:
            table.add_row(row)
        return table

    def _execute_select(self, rows: List[Dict[str, Any]], select_list: List[SelectItemNode]) -> List[Dict[str, Any]]:
        result_rows = []
        for row in rows:
            temp_table = self._create_temp_table(row)
            context = RowContext(temp_table, row)
            selected_row = self._project_row(select_list, context)
            result_rows.append(selected_row)
        print(f"Найдено строк: {len(result_rows)}")
        return result_rows

    def _execute_group_by(self, rows: List[Dict[str, Any]], group_by: List[ExprNode],
                          select_list: List[SelectItemNode], having_clause: Optional[ExprNode]) -> List[Dict[str, Any]]:
        groups = {}

        for row in rows:
            temp_table = self._create_temp_table(row)
            context = RowContext(temp_table, row)
            evaluator = ExpressionEvaluator(context)

            key_parts = []
            for expr in group_by:
                try:
                    value = evaluator.evaluate(expr)
                    key_parts.append(value)
                except Exception:
                    key_parts.append(None)
            key = tuple(key_parts)

            if key not in groups:
                groups[key] = []
            groups[key].append(row)

        result_rows = []

        for group_key, group_rows in groups.items():
            if having_clause:
                group_context = GroupContext(None, group_rows)
                evaluator = ExpressionEvaluator(None, group_context)
                if not bool(evaluator.evaluate(having_clause)):
                    continue

            group_context = GroupContext(None, group_rows)
            evaluator = ExpressionEvaluator(None, group_context)

            row_dict = {}
            for item in select_list:
                if isinstance(item.expr, StarNode):
                    if group_rows:
                        for col, val in group_rows[0].items():
                            row_dict[col] = val
                else:
                    try:
                        value = evaluator.evaluate(item.expr)
                        name = item.alias or str(item.expr)
                        row_dict[name] = value
                    except Exception as e:
                        print(f"Ошибка: {e}")
                        row_dict[str(item.expr)] = None
            result_rows.append(row_dict)

        print(f"Групп: {len(groups)}, результирующих строк: {len(result_rows)}")
        return result_rows

    def _project_row(self, select_list: List[SelectItemNode], context: RowContext) -> Dict[str, Any]:
        result = {}
        evaluator = ExpressionEvaluator(context)

        for item in select_list:
            if isinstance(item.expr, StarNode):
                for col in context.table.column_names:
                    result[col] = context.get_value(col)
                continue

            try:
                value = evaluator.evaluate(item.expr)
                name = item.alias if item.alias else str(item.expr)
                result[name] = value
            except Exception as e:
                print(f"Ошибка при вычислении выражения: {e}")
                name = item.alias or str(item.expr)
                result[name] = None
        return result

    def _apply_distinct(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_rows = []
        seen = set()
        for row in rows:
            row_tuple = tuple(sorted((k, v) for k, v in row.items()))
            if row_tuple not in seen:
                seen.add(row_tuple)
                unique_rows.append(row)
        return unique_rows

    def _apply_order_by(self, rows: List[Dict[str, Any]], order_by: List[OrderingTermNode]) -> List[Dict[str, Any]]:
        def sort_key(row):
            temp_table = self._create_temp_table(row)
            context = RowContext(temp_table, row)
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
            print(f"Ошибка при сортировке: {e}")
            return rows

    def _apply_limit_offset(self, rows: List[Dict[str, Any]],
                            limit_offset: LimitOffsetNode) -> List[Dict[str, Any]]:
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