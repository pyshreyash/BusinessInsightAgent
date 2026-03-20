from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import sqlglot
from sqlglot import exp

from app.db.schema import TABLE_SCHEMAS, ALLOWED_JOIN_CONDITIONS
from app.semantic.loader import SemanticLayer
from app.semantic.metrics import validate_metric_usage


@dataclass(frozen=True)
class SqlValidationError:
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SqlValidationResult:
    ok: bool
    sql: str
    metrics_used: List[str]
    errors: List[SqlValidationError]


def _get_main_select(ast: exp.Expression) -> exp.Select:
    if isinstance(ast, exp.Select):
        return ast
    if isinstance(ast, exp.With):
        inner = ast.this
        if isinstance(inner, exp.Select):
            return inner
    # Fallback: take the first SELECT we find.
    select = ast.find(exp.Select)
    if select is None:
        raise ValueError("No SELECT statement found in SQL.")
    return select


def _collect_cte_names(ast: exp.Expression) -> List[str]:
    names: List[str] = []

    # sqlglot commonly represents `WITH ... SELECT ...` as an `exp.With` node.
    if isinstance(ast, exp.With):
        for cte in ast.expressions or []:
            name = getattr(cte, "alias_or_name", None)
            if name:
                names.append(str(name))
        return names

    with_clause = ast.args.get("with")
    if not with_clause:
        return names

    for cte in with_clause.expressions or []:
        name = getattr(cte, "alias_or_name", None)
        if name:
            names.append(str(name))
    return names


def _build_column_ambiguity_map() -> Dict[str, List[str]]:
    col_to_tables: Dict[str, List[str]] = {}
    for table_name, schema in TABLE_SCHEMAS.items():
        for col in schema.columns.keys():
            col_to_tables.setdefault(col, []).append(table_name)
    return col_to_tables


def validate_sql(*, sql: str, semantic_layer: SemanticLayer) -> SqlValidationResult:
    errors: List[SqlValidationError] = []
    metrics_used, metric_errors = validate_metric_usage(sql, semantic_layer)
    errors.extend([SqlValidationError(code="METRIC_USAGE", message=e) for e in metric_errors])

    try:
        ast = sqlglot.parse_one(sql)
    except Exception as e:
        return SqlValidationResult(ok=False, sql=sql, metrics_used=metrics_used, errors=[SqlValidationError(code="SQL_PARSE", message=str(e))])

    # Ensure main query is SELECT.
    try:
        _ = _get_main_select(ast)
    except Exception as e:
        return SqlValidationResult(ok=False, sql=sql, metrics_used=metrics_used, errors=[SqlValidationError(code="NOT_SELECT", message=str(e))])

    # Basic SELECT * prevention.
    main_select = _get_main_select(ast)
    for proj in main_select.expressions or []:
        if isinstance(proj, exp.Star):
            errors.append(SqlValidationError(code="SELECT_STAR", message="SQL must not use SELECT *"))

    # Collect CTE names so we don't treat them as physical tables.
    cte_names = set(_collect_cte_names(ast))

    # Map aliases/tables.
    alias_to_table: Dict[str, str] = {}
    for table in ast.find_all(exp.Table):
        tname = table.name
        alias = table.alias_or_name
        if alias:
            alias_to_table[str(alias)] = str(tname)

    # Validate physical tables existence.
    for table in ast.find_all(exp.Table):
        tname = table.name
        if tname in cte_names:
            continue
        if tname not in TABLE_SCHEMAS:
            errors.append(
                SqlValidationError(code="UNKNOWN_TABLE", message=f"SQL references unknown table `{tname}`.")
            )

    # Validate columns.
    col_ambiguity = _build_column_ambiguity_map()
    for col in ast.find_all(exp.Column):
        col_name = col.name
        table_part = col.table

        if table_part:
            resolved = alias_to_table.get(str(table_part))
            if not resolved:
                # If table_part refers to physical name directly, use it.
                if str(table_part) in TABLE_SCHEMAS:
                    resolved = str(table_part)
                else:
                    errors.append(
                        SqlValidationError(
                            code="UNKNOWN_TABLE_ALIAS",
                            message=f"Column `{col_name}` references unknown table/alias `{table_part}`.",
                        )
                    )
                    continue
            table_schema = TABLE_SCHEMAS.get(resolved)
            if not table_schema:
                errors.append(
                    SqlValidationError(code="UNKNOWN_TABLE", message=f"Column references unknown table `{resolved}`.")
                )
                continue
            if col_name not in table_schema.columns:
                errors.append(
                    SqlValidationError(
                        code="UNKNOWN_COLUMN",
                        message=f"Column `{resolved}.{col_name}` does not exist in schema.",
                    )
                )
        else:
            possible_tables = col_ambiguity.get(col_name, [])
            if len(possible_tables) != 1:
                errors.append(
                    SqlValidationError(
                        code="AMBIGUOUS_COLUMN",
                        message=f"Unqualified column `{col_name}` is ambiguous (appears in {possible_tables}).",
                    )
                )
            else:
                table_name = possible_tables[0]
                if col_name not in TABLE_SCHEMAS[table_name].columns:
                    errors.append(
                        SqlValidationError(
                            code="UNKNOWN_COLUMN",
                            message=f"Column `{table_name}.{col_name}` does not exist in schema.",
                        )
                    )

    # Join validation.
    for join in ast.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue

        if not isinstance(on_expr, exp.EQ):
            errors.append(
                SqlValidationError(
                    code="UNSUPPORTED_JOIN_CONDITION",
                    message="Join condition must be a simple equality for deterministic validation.",
                )
            )
            continue

        left = on_expr.left
        right = on_expr.right
        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
            errors.append(
                SqlValidationError(
                    code="UNSUPPORTED_JOIN_CONDITION",
                    message="Join ON must compare two columns for deterministic validation.",
                )
            )
            continue

        def resolve_col_table(c: exp.Column) -> Tuple[Optional[str], str]:
            if c.table:
                return str(c.table), c.name
            return None, c.name

        left_table_part, left_col = resolve_col_table(left)
        right_table_part, right_col = resolve_col_table(right)

        # Resolve table-part to physical table name.
        def resolve_physical(table_part: Optional[str]) -> Optional[str]:
            if not table_part:
                return None
            return alias_to_table.get(table_part) or (table_part if table_part in TABLE_SCHEMAS else None)

        l_phys = resolve_physical(left_table_part)
        r_phys = resolve_physical(right_table_part)
        if not l_phys or not r_phys:
            # If we cannot resolve deterministically, don't block MVP (schema mismatch should be caught elsewhere).
            continue

        allowed = any(
            (l_phys, left_col, r_phys, right_col) == jc or (r_phys, right_col, l_phys, left_col) == jc
            for jc in ALLOWED_JOIN_CONDITIONS
        )
        if not allowed:
            errors.append(
                SqlValidationError(
                    code="INVALID_JOIN",
                    message=f"Join condition `{l_phys}.{left_col} = {r_phys}.{right_col}` is not allowed.",
                )
            )

    ok = len(errors) == 0
    return SqlValidationResult(ok=ok, sql=sql, metrics_used=metrics_used, errors=errors)

