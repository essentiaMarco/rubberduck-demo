# Django #11062 — Bug report and debug summary

## Bug report (from GitHub)

**Issue:** [django/django #11062](https://github.com/django/django/issues/11062) — *Subquery resolving refactor and bug fixing*

**Summary:** Refactor of subquery resolving logic into `Query`, fixing two tickets:

1. **#21703** — Crash when excluding a related field with `F()` (e.g. `exclude(tag__note__note=F('name'))`). Fix: resolve `OuterRef` in the inner query used by `split_exclude`.
2. **#30188** — `AssertionError` on `set_source_expressions` when aggregating over a subquery annotation. Cause: `rewrite_cols` recursed into `Subquery` and called `set_source_expressions` on it; `Subquery` asserts `not exprs`. Fix: treat `Subquery` like `Col` in `rewrite_cols` (select it under a new alias instead of recursing).

Additional follow-up commits: prevent double annotation when aggregating over subquery, avoid unnecessary GROUP BY, reuse annotation aliases in aggregation filters (#30246).

---

## Root cause (from MCP analysis)

### 1. #21703 — exclude with F() crash

**Location:** `django/db/models/sql/query.py` — `split_exclude()`

**Behavior:** For excludes like `exclude(tag__note__note=F('name'))`, the RHS is an `F('name')` that refers to the *outer* row. The inner subquery built by `split_exclude` was given this `F()` as-is. `F()` is resolved in the *current* query; in the inner query there is no such column, so resolution failed and caused a crash.

**Fix (commit f19a494):** At the start of `split_exclude`, if the filter RHS is an `F`, wrap it in `OuterRef` so the inner query can resolve it against the outer query:

```python
filter_lhs, filter_rhs = filter_expr
if isinstance(filter_rhs, F):
    filter_expr = (filter_lhs, OuterRef(filter_rhs.name))
```

**Imports:** Add `OuterRef` to the expression imports in `query.py`.

---

### 2. #30188 — AssertionError when aggregating over subquery annotation

**Location:** `django/db/models/sql/query.py` — `rewrite_cols()`

**Behavior:** When aggregating over an annotation that is a `Subquery` (e.g. `annotate(ceo_salary=Subquery(...)).aggregate(Count('pk', filter=Q(ceo_salary__gt=20)))`), `get_aggregation` builds an inner/outer query and calls `rewrite_cols` on the annotation. The condition for “add a new column/Ref” was:

```python
elif isinstance(expr, Col) or (expr.contains_aggregate and not expr.is_summary):
```

For a `Subquery` this was false, so the code went to the `else` branch and called `rewrite_cols(expr, col_cnt)` on the Subquery. That path eventually called `annotation.set_source_expressions(new_exprs)`. The `Subquery` class in `django/db/models/expressions.py` defines `set_source_expressions(self, exprs): assert not exprs`, so any non-empty `exprs` triggered the AssertionError.

**Fix (commit bdc07f1):** Treat `Subquery` like `Col`: select it under a new alias and use a `Ref`, instead of recursing:

```python
elif isinstance(expr, (Col, Subquery)) or (expr.contains_aggregate and not expr.is_summary):
```

**Imports:** Add `Subquery` to the expression imports in `query.py`.

---

### 3. Refs #30188 — Double annotation (commit d1e9c25)

**Location:** `django/db/models/sql/query.py` — `get_aggregation()`

**Fix:** Set the inner query’s annotation mask before processing: `inner_query.set_annotation_mask(self.annotation_select)`, and when moving an aggregate to the outer query, remove that alias from the mask: `annotation_select_mask.remove(alias)` (using a copy of the mask). This prevents the subquery from being annotated twice in the inner query.

---

### 4. Refs #30188 — Avoid GROUP BY when not needed (commit 3f32154)

**Location:** `django/db/models/sql/query.py` — `get_aggregation()`

**Fix:** Only force GROUP BY on the inner query when there are *aggregate* annotations (e.g. Sum, Count), not for non-aggregate annotations like plain `Subquery`. Use:

- `existing_annotations = [annotation for ...]` (list, not `any()`),
- `has_existing_aggregate_annotations = any(getattr(annotation, 'contains_aggregate', True) for annotation in existing_annotations)`,
- apply `inner_query.group_by = (...)` only when `inner_query.default_cols and has_existing_aggregate_annotations`.

---

## Files to change (for a minimal fix set)

| File | Change |
|------|--------|
| `django/db/models/sql/query.py` | 1) Import `OuterRef` (and `Subquery` for #30188). 2) In `split_exclude`, add the F→OuterRef handling. 3) In `rewrite_cols`, add `Subquery` to the `isinstance(expr, (Col, Subquery))` branch. 4) In `get_aggregation`, set annotation mask, use `existing_annotations` and `has_existing_aggregate_annotations`, and update the mask when moving aggregates (as in commits above). |

---

## Verification

- **#21703:** Test `exclude(tag__note__note=F('name'))` (e.g. `test_exclude_reverse_fk_field_ref` in `tests/queries/tests.py`).
- **#30188:** Test `annotate(ceo_salary=Subquery(...)).aggregate(Count('pk', filter=Q(ceo_salary__gt=20)))` (e.g. `test_aggregate_subquery_annotation` in `tests/expressions/tests.py`).

---

*Generated using the Django #11062 bug report and Rubberduck MCP semantic/codebase analysis.*
