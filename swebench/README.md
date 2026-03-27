# SWE-bench + Rubberduck MCP

Run SWE-bench Verified (Django 26 tasks) with Claude Code and Rubberduck MCP tools in Daytona sandboxes.

## Why MCP wasn’t used in the first run

The sandbox `.claude.json` had `"Authorization": "Bearer ${RUBBERDUCK_TOKEN}"` as a **literal string**. YAML doesn’t expand `${RUBBERDUCK_TOKEN}`, so the token never reached the MCP client. Two changes fix this:

1. **Job config** – Removed `env: RUBBERDUCK_TOKEN: "${RUBBERDUCK_TOKEN}"` from the agent so the placeholder isn’t passed into the sandbox.
2. **Agent** – If the env var is missing or literally `"${RUBBERDUCK_TOKEN}"`, the agent falls back to the embedded token so MCP still works.

For a clean run, pass the token via the CLI so the **shell** expands it before Harbor runs.

## Model

The job configs use `anthropic/claude-sonnet-4-6`. Older IDs like `claude-3-5-sonnet-20241022` can cause “model may not exist or you may not have access” in the sandbox; if the agent exits immediately with that message, switch to a current model (e.g. `claude-sonnet-4-6`).

## Fix and rerun

### 1. Pass the token into the sandbox (recommended)

```bash
cd /Users/marcomarinucci/repos/rubberduck-demo
export RUBBERDUCK_TOKEN='your-actual-token'
harbor run -c swebench/job_config.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN
```

Without `--ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN`, the sandbox may get no token (or a literal placeholder); the agent’s fallback token is used so MCP can still work.

### 2. Rerun the full job (all 26 Django tasks)

Same as above:

```bash
export RUBBERDUCK_TOKEN='your-token'
harbor run -c swebench/job_config.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN
```

Results go to a new `jobs/YYYY-MM-DD__HH-MM-SS/` directory.

### 3. Rerun only some tasks (e.g. django-15098)

Edit `swebench/job_config.yaml` and set `task_names` to the tasks you want:

```yaml
datasets:
  - name: swebench-verified
    version: "1.0"
    registry:
      url: "https://raw.githubusercontent.com/laude-institute/harbor/main/registry.json"
    task_names:
      - django__django-15098
```

Then run:

```bash
harbor run -c swebench/job_config.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN
```

To run a single task, use a one-element list as above. To exclude tasks, remove them from `task_names` and run the full job again.

**Quick single-task run for django-10554:**

```bash
harbor run -c swebench/job_config_single_10554.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN
```

### 4. Using the correct commit (instance) for MCP

SWE-bench tasks have a **base commit**; analysis must use that commit so the code matches the testbed. With the **semantic** MCP, use `load_repo(..., instance_id="owner__repo_<short_sha>")` so the server loads that snapshot instead of HEAD.

- **Format:** `instance_id` = `owner__repo_` + first 8 characters of the base commit.  
  Example: task base commit `14d026cccb144c6877294ba4cd4e03ebf0842498` → `instance_id="essentiaMarco__django_14d026cc"`.
- **Availability:** The Rubberduck semantic server must have that instance. List with `list_repos(include_instances=True)`. If the instance for your task’s base commit is missing, the codebase at that branch/commit needs to be indexed on the server so the instance exists.
- The agent instruction now tells the model to use this `instance_id` when the task specifies a base commit.

### 5. Solution for django-10554 (union + order_by)

**Bug:** Union queryset with ordering breaks when you do `qs.order_by().values_list('pk', flat=True)` and then re-evaluate `qs`: `ProgrammingError: ORDER BY position 4 is not in select list`.

**Cause:** In `get_combinator_sql`, when the main query has a limited select (`values_select`), that select is copied onto each combined subquery via `set_values(...)`. The subqueries can still have their own `order_by` (e.g. from `union(B.order_by('order'))`). After `set_values`, the subquery’s select list is reduced (e.g. to `pk` only), but its `order_by` is left unchanged, so the compiler emits `ORDER BY 4` while the select has only one column.

**Fix:** After copying the main query’s select onto a combined query, clear that combined query’s ordering so ORDER BY is not applied to a reduced select. In `django/db/models/sql/compiler.py`, inside `get_combinator_sql`, after the `compiler.query.set_values(...)` block, add:

```python
compiler.query.clear_ordering(force_empty=True)
```

A ready-made patch is in `swebench/patches/django-10554-union-order-by.patch`. From the Django repo root (e.g. `testbed/` in the sandbox): `git apply /path/to/swebench/patches/django-10554-union-order-by.patch`.

### 6. Optional: limit concurrency

```bash
# 4 trials at a time instead of 32
harbor run -c swebench/job_config.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN -n 4
```

(`orchestrator.n_concurrent_trials` in the YAML also sets concurrency.)

## Summary

| Goal                    | Command |
|-------------------------|--------|
| Fix MCP auth            | Run with `--ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN` (and `export RUBBERDUCK_TOKEN`). |
| Rerun full 26 tasks     | `harbor run -c swebench/job_config.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN` |
| Rerun only django-10554 | `harbor run -c swebench/job_config_single_10554.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN` |
| Rerun only django-15098 | Set `task_names: [django__django-15098]` in the YAML, then same `harbor run` command. |
