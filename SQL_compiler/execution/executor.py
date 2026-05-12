from typing import List, Dict, Any, Optional

from SQL_compiler.execution.table import Table
from SQL_compiler.execution.execution_context import RowContext, ExpressionEvaluator, GroupContext
from SQL_compiler.parsing.ast_nodes import *


class QueryExecutor:
    def __init__(self, tables: Dict[str, Table]):
        self.tables = tables

    def execute(self, stmt: SelectStmtNode) -> List[Dict[str, Any]]:
        if not isinstance(stmt, SelectStmtNode):
            raise TypeError(f"Expected SelectStmtNode, got {type(stmt)}")

        if stmt.from_node is None or not stmt.from_node.tables:
            return self._execute_without_from(stmt)

        source_rows = self._execute_from_and_joins(stmt.from_node, stmt.where_clause)

        if stmt.group_by:
            result_rows = self._execute_group_by(
                source_rows,
                stmt.group_by,
                stmt.select_list,
                stmt.having_clause,
            )

            if stmt.distinct:
                result_rows = self._apply_distinct(result_rows)

            if stmt.order_by:
                result_rows = self._apply_order_by(result_rows, stmt.order_by)

            if stmt.limit_offset:
                result_rows = self._apply_limit_offset(result_rows, stmt.limit_offset)

            return result_rows

        if stmt.order_by:
            source_rows = self._apply_order_by(source_rows, stmt.order_by)

        result_rows = self._execute_select(source_rows, stmt.select_list)

        if stmt.distinct:
            result_rows = self._apply_distinct(result_rows)

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

    def _execute_from_and_joins(
            self,
            from_node: FromNode,
            where_clause: Optional[AstNode],
    ) -> List[Dict[str, Any]]:
        if not from_node.tables:
            return []

        first_table_node = from_node.tables[0]

        if isinstance(first_table_node, TableBaseNode):
            allow_unqualified = len(from_node.tables) == 1

            current_rows = self._get_table_rows_with_alias(
                first_table_node,
                allow_unqualified=allow_unqualified,
            )

            if hasattr(first_table_node, "joins") and first_table_node.joins:
                for join_node in first_table_node.joins:
                    current_rows = self._process_join(current_rows, join_node)

        elif isinstance(first_table_node, TableSubqueryNode):
            current_rows = self._get_subquery_rows(first_table_node)
        else:
            current_rows = []

        for table_node in from_node.tables[1:]:
            if isinstance(table_node, TableBaseNode):
                right_rows = self._get_table_rows_with_alias(
                    table_node,
                    allow_unqualified=False,
                )
                current_rows = self._cross_join(current_rows, right_rows)
            elif isinstance(table_node, TableSubqueryNode):
                right_rows = self._get_subquery_rows(table_node)
                current_rows = self._cross_join(current_rows, right_rows)
            elif isinstance(table_node, JoinNode):
                current_rows = self._process_join(current_rows, table_node)

        if where_clause and current_rows:
            self._precompute_subqueries(where_clause)

            filtered_rows = []
            for row in current_rows:
                temp_table = self._create_temp_table(row)
                context = RowContext(temp_table, row, self.tables)
                evaluator = ExpressionEvaluator(context)
                try:
                    if bool(evaluator.evaluate(where_clause)):
                        filtered_rows.append(row)
                except Exception:
                    continue
            current_rows = filtered_rows

        return current_rows if current_rows else []

    def _precompute_subqueries(self, node: AstNode) -> None:
        """Найти и вычислить все подзапросы в выражении"""
        if isinstance(node, InSubqueryNode):
            # Вычислить подзапрос и сохранить результат
            # (можно использовать тот же кэш)
            pass
        else:
            for child in node.childs:
                self._precompute_subqueries(child)

    def _get_subquery_rows(self, table_node: TableSubqueryNode) -> List[Dict[str, Any]]:
        try:
            sub_executor = QueryExecutor(self.tables)
            rows = sub_executor.execute(table_node.query)
        except Exception as e:
            print(f"Subquery error: {e}")
            return []

        alias = table_node.alias
        if not rows:
            return []

        result = []
        for row in rows:
            prefixed_row = {}
            for col, val in row.items():
                # Сохраняем оригинальное имя
                prefixed_row[col] = val
                # Добавляем с псевдонимом
                if alias:
                    prefixed_row[f"{alias}.{col}"] = val
                # Также добавляем без префикса для удобства
                if '.' in col:
                    simple_name = col.split('.')[-1]
                    prefixed_row[simple_name] = val
            result.append(prefixed_row)
        return result

    def _cross_join(self, left_rows: List[Dict[str, Any]], right_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not left_rows:
            return right_rows[:]
        if not right_rows:
            return left_rows[:]

        result = []
        for left_row in left_rows:
            for right_row in right_rows:
                result.append(self._merge_rows(left_row, right_row))
        return result

    def _get_table_rows_with_alias(
            self,
            table_node: TableBaseNode,
            allow_unqualified: bool = False,
    ) -> List[Dict[str, Any]]:
        table = self.tables.get(table_node.name)
        if table is None:
            return []

        alias = table_node.alias or table_node.name
        rows = []

        for row in table.rows:
            prefixed_row = {}
            for col, val in row.items():
                # Всегда добавляем с алиасом (или именем таблицы, если алиаса нет)
                prefixed_row[f"{alias}.{col}"] = val

                # Если алиас отличается от имени таблицы, добавляем также с именем таблицы
                if alias != table.name:
                    prefixed_row[f"{table.name}.{col}"] = val

                # Если разрешены неполные имена
                if allow_unqualified:
                    prefixed_row[col] = val

            rows.append(prefixed_row)

        return rows

    def _collect_keys(self, rows: List[Dict[str, Any]]) -> List[str]:
        keys = []
        seen = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        return keys

    def _merge_rows(self, left_row: Dict[str, Any], right_row: Dict[str, Any]) -> Dict[str, Any]:
        merged = left_row.copy()
        for k, v in right_row.items():
            if k not in merged:
                merged[k] = v
        return merged

    def _row_matches_condition(self, merged: Dict[str, Any], condition: Optional[AstNode]) -> bool:
        if condition is None:
            return True

        temp_table = self._create_temp_table(merged)
        context = RowContext(temp_table, merged, self.tables)
        evaluator = ExpressionEvaluator(context)
        try:
            return bool(evaluator.evaluate(condition))
        except Exception:
            return False

    def _null_extended_row(self, base_row: Dict[str, Any], null_keys: List[str]) -> Dict[str, Any]:
        row = base_row.copy()
        for key in null_keys:
            if key not in row:
                row[key] = None
        return row

    def _process_join(self, left_rows: List[Dict[str, Any]], join_node: JoinNode) -> List[Dict[str, Any]]:
        if isinstance(join_node.table, TableBaseNode):
            right_rows = self._get_table_rows_with_alias(
                join_node.table,
                allow_unqualified=False,
            )
            right_null_keys = self._collect_keys(right_rows)
        elif isinstance(join_node.table, TableSubqueryNode):
            right_rows = self._get_subquery_rows(join_node.table)
            right_null_keys = self._collect_keys(right_rows)
        else:
            right_rows = []
            right_null_keys = []

        join_type = join_node.join_type.upper().strip()

        if join_type in ("JOIN", "INNER", "INNER JOIN"):
            join_type = "INNER JOIN"
        elif join_type in ("LEFT", "LEFT JOIN", "LEFT OUTER JOIN"):
            join_type = "LEFT JOIN"
        elif join_type in ("RIGHT", "RIGHT JOIN", "RIGHT OUTER JOIN"):
            join_type = "RIGHT JOIN"
        elif join_type in ("CROSS", "CROSS JOIN"):
            join_type = "CROSS JOIN"

        if join_type == "CROSS JOIN":
            return self._cross_join(left_rows, right_rows)

        if join_type == "RIGHT JOIN":
            # Переворачиваем JOIN и используем LEFT JOIN
            swapped = self._process_join_with_type(
                right_rows,
                left_rows,
                join_node.condition,
                "LEFT JOIN",
                self._collect_keys(left_rows),
            )
            return swapped

        return self._process_join_with_type(
            left_rows,
            right_rows,
            join_node.condition,
            join_type,
            right_null_keys,
        )

    def _process_join_with_type(
            self,
            left_rows: List[Dict[str, Any]],
            right_rows: List[Dict[str, Any]],
            condition: Optional[AstNode],
            join_type: str,
            right_null_keys: List[str],
    ) -> List[Dict[str, Any]]:
        if not left_rows:
            return []

        if not right_rows:
            if join_type == "LEFT JOIN":
                return [self._null_extended_row(left_row, right_null_keys) for left_row in left_rows]
            return []

        result = []

        for left_row in left_rows:
            matched = False

            for right_row in right_rows:
                merged = self._merge_rows(left_row, right_row)

                if not self._row_matches_condition(merged, condition):
                    continue

                matched = True
                result.append(merged)

            if join_type == "LEFT JOIN" and not matched:
                result.append(self._null_extended_row(left_row, right_null_keys))

        return result

    def _create_temp_table(self, row: Dict[str, Any]) -> Table:
        table = Table("temp")
        for col, value in row.items():
            if value is None:
                col_type = str
            else:
                col_type = type(value)
            table.add_column(col, col_type)
        table.add_row(row)
        return table

    def _execute_select(self, rows: List[Dict[str, Any]], select_list: List[SelectItemNode]) -> List[Dict[str, Any]]:
        print(f"[DEBUG] select_list: {select_list}")
        print(f"[DEBUG] select_list types: {[type(item) for item in select_list]}")
        result_rows = []
        for row in rows:
            temp_table = self._create_temp_table(row)
            context = RowContext(temp_table, row, self.tables)
            selected_row = self._project_row(select_list, context)
            result_rows.append(selected_row)
        return result_rows

    def _execute_group_by(
            self,
            rows: List[Dict[str, Any]],
            group_by: List[ExprNode],
            select_list: List[SelectItemNode],
            having_clause: Optional[ExprNode],
    ) -> List[Dict[str, Any]]:
        groups = {}

        # Группировка
        for row in rows:
            temp_table = self._create_temp_table(row)
            context = RowContext(temp_table, row, self.tables)
            evaluator = ExpressionEvaluator(context)

            key_parts = []
            for expr in group_by:
                try:
                    value = evaluator.evaluate(expr)
                    if isinstance(value, (list, dict)):
                        value = str(value)
                    key_parts.append(value)
                except Exception as e:
                    print(f"Ошибка при вычислении GROUP BY: {e}")
                    key_parts.append(None)

            key = tuple(key_parts)
            groups.setdefault(key, []).append(row)

        print(f"[DEBUG GROUP] Found {len(groups)} groups")

        result_rows = []

        # Обработка групп с HAVING
        for group_key, group_rows in groups.items():
            print(f"[DEBUG GROUP] Processing group with key: {group_key}, size: {len(group_rows)}")

            group_context = GroupContext(group_rows)

            # Проверяем HAVING через ExpressionEvaluator
            if having_clause:
                evaluator = ExpressionEvaluator(group_context=group_context)
                try:
                    # Если having_clause - список, комбинируем условия через AND
                    if isinstance(having_clause, list):
                        having_result = True
                        for clause in having_clause:
                            clause_result = evaluator.evaluate(clause)
                            having_result = having_result and bool(clause_result)
                            if not having_result:
                                break
                    else:
                        having_result = evaluator.evaluate(having_clause)

                    print(f"[DEBUG HAVING] Condition result: {having_result} (type: {type(having_result)})")

                    if not bool(having_result):
                        print(f"[DEBUG HAVING] Group rejected (condition False)")
                        continue
                    else:
                        print(f"[DEBUG HAVING] Group accepted (condition True)")
                except Exception as e:
                    print(f"Ошибка при вычислении HAVING: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            # Формируем результат через ExpressionEvaluator
            row_dict = {}
            evaluator = ExpressionEvaluator(group_context=group_context)
            for item in select_list:
                if isinstance(item.expr, StarNode):
                    if group_rows:
                        seen_columns = set()
                        for col, val in group_rows[0].items():
                            # Берем только простое имя колонки (без префикса)
                            simple_name = col.split('.')[-1]
                            # Добавляем только если еще не добавляли
                            if simple_name not in seen_columns:
                                row_dict[simple_name] = val
                                seen_columns.add(simple_name)
                    continue

                try:
                    evaluator = ExpressionEvaluator(group_context=group_context)
                    value = evaluator.evaluate(item.expr)

                    # ОТЛАДКА: выводим информацию об expression
                    print(f"[DEBUG NAME] item.expr type: {type(item.expr)}")
                    print(f"[DEBUG NAME] item.expr: {item.expr}")
                    print(f"[DEBUG NAME] item.alias: {item.alias}")
                    if item.alias:
                        name = item.alias
                        print(f"[DEBUG NAME] Using alias: {name}")
                    elif isinstance(item.expr, FuncCallNode):
                        func_name = item.expr.name
                        if item.expr.args:
                            arg_name = self._extract_arg_name(item.expr.args[0])
                            name = f"{func_name}({arg_name})"
                        else:
                            name = f"{func_name}()"
                        print(f"[DEBUG NAME] Generated function name: {name}")
                    elif isinstance(item.expr, IdentNode):
                        name = item.expr.name
                        print(f"[DEBUG NAME] IdentNode name: {name}")
                    elif isinstance(item.expr, CompoundIdentNode):
                        name = item.expr.full_name
                        print(f"[DEBUG NAME] CompoundIdentNode name: {name}")
                    else:
                        name = str(item.expr)
                        print(f"[DEBUG NAME] Fallback str() name: {name}")

                    row_dict[name] = value
                    print(f"[DEBUG SELECT] {name} = {value}")
                except Exception as e:
                    print(f"Ошибка при вычислении SELECT: {e}")
                    import traceback
                    traceback.print_exc()
                    name = item.alias or str(item.expr)
                    row_dict[name] = None

            result_rows.append(row_dict)

        print(f"[DEBUG GROUP] Final result rows: {len(result_rows)}")
        return result_rows

    def _extract_arg_name(self, arg) -> str:
        """Извлечь имя из аргумента функции"""
        # Если arg - список, берем первый элемент
        if isinstance(arg, list):
            if not arg:
                return "*"
            arg = arg[0]

        if isinstance(arg, IdentNode):
            return arg.name
        elif isinstance(arg, CompoundIdentNode):
            return arg.full_name
        elif isinstance(arg, StarNode):
            return "*"
        else:
            return str(arg)

    def _project_row(self, select_list: List[SelectItemNode], context: RowContext) -> Dict[str, Any]:
        result = {}
        evaluator = ExpressionEvaluator(context)

        for item in select_list:
            if isinstance(item.expr, StarNode):
                seen_columns = set()
                for col in context.table.column_names:
                    simple_name = col.split('.')[-1]
                    if simple_name not in seen_columns:
                        result[simple_name] = context.get_value(col)
                        seen_columns.add(simple_name)
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
            row_tuple = tuple(sorted((k, self._hashable_value(v)) for k, v in row.items()))
            if row_tuple not in seen:
                seen.add(row_tuple)
                unique_rows.append(row)
        return unique_rows

    def _hashable_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return tuple(self._hashable_value(v) for v in value)
        if isinstance(value, dict):
            return tuple(sorted((k, self._hashable_value(v)) for k, v in value.items()))
        return value

    def _sort_key_value(self, value: Any) -> Any:
        if value is None:
            return (1, None)
        if isinstance(value, (int, float, str, bool)):
            return (0, value)
        return (0, str(value))

    def _apply_order_by(self, rows: List[Dict[str, Any]], order_by: List[OrderingTermNode]) -> List[Dict[str, Any]]:
        if not rows or not order_by:
            return rows

        sorted_rows = rows[:]

        for term in reversed(order_by):
            def key_func(row):
                temp_table = self._create_temp_table(row)
                context = RowContext(temp_table, row, self.tables)
                evaluator = ExpressionEvaluator(context)
                try:
                    value = evaluator.evaluate(term.expr)
                except Exception:
                    value = None
                return self._sort_key_value(value)

            reverse = str(term.direction).upper() == "DESC"
            sorted_rows = sorted(sorted_rows, key=key_func, reverse=reverse)

        return sorted_rows

    def _apply_limit_offset(
            self,
            rows: List[Dict[str, Any]],
            limit_offset: LimitOffsetNode,
    ) -> List[Dict[str, Any]]:
        evaluator = ExpressionEvaluator(None)

        try:
            limit_val = evaluator.evaluate(limit_offset.limit)
            limit = int(limit_val) if limit_val is not None else len(rows)
        except Exception:
            limit = len(rows)

        offset = 0
        if limit_offset.offset is not None:
            try:
                offset_val = evaluator.evaluate(limit_offset.offset)
                offset = int(offset_val) if offset_val is not None else 0
            except Exception:
                offset = 0

        start = min(offset, len(rows))
        end = min(start + limit, len(rows))
        return rows[start:end]
