# Objective MCP-only debug test — Runbook

This runbook lets you run a **fair, objective** test in a **new chat**: the model must use **only** the bug report and MCP tools to find and fix the bug. No looking up the solution online.

---

## 1. Rules (enforce in the prompt)

- **Do not** fetch the GitHub PR, commits, or any “fix” from the internet.
- **Do not** search the web for “Django 11062 fix” or similar.
- Use **only**:
  - The bug report text below (problem statement and ticket numbers).
  - Rubberduck MCP tools: `load_repo`, `analyze_code`, `localize_and_fix_bug`, `search_code`, `read_source`, `query_action`, etc.
- **Mandatory:** Load the repo at the **exact base commit** of the SWE-bench instance. You must use `load_repo(..., instance_id='<INSTANCE_ID>')` where `INSTANCE_ID` is the one for this task (see §5). Do **not** use `load_repo` without `instance_id` or with a different instance — analyzing HEAD or another commit makes the test invalid.
- Repo: **essentiaMarco/django** (fork) or **django/django**; the prompt must contain the correct **instance_id** for **django__django-11062** so the model is forced to analyze the code at that commit.
- Success criterion: **tests pass** when run at that same base commit after applying the fix.

---

## 2. Bug report (copy this only — no spoilers)

**Standard version** (matches GitHub issue wording; mentions ticket numbers and some keywords):

**Issue:** django/django #11062 — *Subquery resolving refactor and bug fixing*

This work addresses two tickets:

- **#21703** — Crash when excluding a related field with `F()`. Example:  
  `SomeModel.objects.exclude(tag__note__note=F('name'))`  
  The fix involves resolving `OuterRef` in the inner query used by `split_exclude`.

- **#30188** — `AssertionError` on `set_source_expressions` when aggregating over a subquery annotation. Example: annotate with a `Subquery`, then call `.aggregate(Count('pk', filter=Q(ceo_salary__gt=20)))`. The resolving logic push-down addresses the AssertionError; a further fix was needed for a broken reference caused by `rewrite_cols` (either clear the inner query’s annotations before rewriting or reuse existing refs to avoid double work).

Implement fixes for both #21703 and #30188 using only the codebase and MCP tools. Do not look up the merged PR or commits.

**Strict version** (minimal hints — use for a harder objective test):

- **#21703** — Crash when excluding a related field with `F()`, e.g. `exclude(tag__note__note=F('name'))`. Find and fix the crash.
- **#30188** — `AssertionError` on `set_source_expressions` when aggregating over a subquery annotation (e.g. annotate with `Subquery(...)` then `.aggregate(Count('pk', filter=Q(...)))`). Find and fix the AssertionError and any related broken reference.

Use only the codebase and MCP tools. Do not look up the PR or commits.

---

## 3. Prompt to paste in a new chat

Copy-paste the following into a **new** Cursor chat (no prior context about the fix):

```
I want to run an objective MCP-only debugging test. Follow these rules strictly:

RULES:
- Do NOT fetch the GitHub PR #11062, its commits, or any "fix" from the internet. No web search for the solution.
- Use ONLY the bug report I paste below and the Rubberduck MCP tools (user-rubberduck-codebase-intelligence and user-rubberduck-semantic-intelligence) to find the root cause and implement the fix.
- You MUST load the repo at the base commit for this task. Use load_repo(repo='essentiaMarco/django', instance_id='<INSTANCE_ID>', subpath=...) where <INSTANCE_ID> is the one for django__django-11062 (see below). Do NOT call load_repo without instance_id or you will analyze the wrong commit.
- INSTANCE_ID for this run: [FILL IN BEFORE PASTING — see §5]
- After proposing code changes, run the relevant Django tests (see below) and tell me pass/fail.

BUG REPORT:
---
Issue: django/django #11062 — Subquery resolving refactor and bug fixing.

Addresses two tickets:

#21703 — Crash when excluding a related field with F(). Example: SomeModel.objects.exclude(tag__note__note=F('name')). The fix involves resolving OuterRef in the inner query used by split_exclude.

#30188 — AssertionError on set_source_expressions when aggregating over a subquery annotation. Example: annotate with a Subquery then .aggregate(Count('pk', filter=Q(ceo_salary__gt=20))). The resolving logic push-down addresses the AssertionError; another fix was needed for a broken reference caused by rewrite_cols (clear inner query annotations before rewrite or reuse existing refs).

Implement fixes for #21703 and #30188 using only the codebase and MCP tools. Do not look up the merged PR or commits.
---

Use MCP to: (1) load the repo with instance_id='<INSTANCE_ID>' (required — see §5), (2) find split_exclude and rewrite_cols and related code, (3) understand why the crash/AssertionError happens, (4) propose minimal code changes, (5) run the verification tests at the same commit and report results.
```

**Strict prompt** (use with the strict bug report in §2; no method names; **replace `<INSTANCE_ID>`** with the value from §5):

```
I want an objective MCP-only debugging test. Rules: Do NOT fetch the GitHub PR #11062, its commits, or any fix from the internet. Use ONLY the bug report below and Rubberduck MCP tools to find the root cause and implement the fix. You MUST call load_repo(repo='essentiaMarco/django', instance_id='<INSTANCE_ID>', ...) so analysis is at the correct base commit for django__django-11062 — do not load without instance_id. Repo owner: essentiaMarco (or your fork). After proposing changes, run the Django tests for #21703 and #30188 and report pass/fail.

BUG REPORT:
#21703 — Crash when excluding a related field with F(), e.g. exclude(tag__note__note=F('name')). Find and fix the crash.
#30188 — AssertionError on set_source_expressions when aggregating over a subquery annotation (e.g. annotate with Subquery(...) then .aggregate(Count('pk', filter=Q(...)))). Find and fix the AssertionError and any related broken reference.

Use only the codebase and MCP. Do not look up the PR or commits. Always use instance_id='<INSTANCE_ID>' when loading the repo (replace with the correct value for this task).
```

---

## 4. How to verify (objective pass/fail)

After the model proposes a fix:

1. **Checkout the same base commit** as the instance_id you used (e.g. the commit that matches `essentiaMarco__django_<shortsha>` — the full SHA is in the preindex/get_index_status output). The fix must be applied and tested at that exact commit.
2. **Apply the proposed patch** to `django/db/models/sql/query.py` (and any other files the model changes).
3. **Run the relevant tests:**
   - #21703:  
     `python tests/runtests.py queries.tests.Queries1Tests.test_exclude_reverse_fk_field_ref -v 2`
   - #30188:  
     `python tests/runtests.py expressions.tests.BasicExpressionTests.test_aggregate_subquery_annotation -v 2`
4. If both tests pass → **objective pass**. If either fails or the model looked up the fix → **fail**.

(If the test names differ in your Django version, search the Django repo for `exclude.*F(` and `aggregate_subquery_annotation` to find the correct test.)

---

## 5. Required: Get and use the correct instance_id

For an objective test, the model **must** analyze the code at the **exact base commit** of the SWE-bench instance. That only happens if you force the correct **instance_id** in the prompt.

### How to get the instance_id for django__django-11062

1. **Get the base commit** for the instance:
   - From Harbor: the task for `django__django-11062` has a `base_commit` (or the dataset/task.toml specifies it).
   - From your fork: ensure branch **swebench/django-11062** exists and points to that base commit (create it from the SWE-bench prescribed commit if needed).
2. **Index that branch** (so the semantic server has that snapshot):
   - Codebase-intelligence: `preindex_repository(repo="essentiaMarco/django", branch="swebench/django-11062")`.
   - Wait until Phase 1 (and Phase 2 if desired) is READY.
3. **Read the instance_id** from the preindex response or from:
   - `get_index_status(repo="essentiaMarco/django", branch="swebench/django-11062")`  
   - The result includes e.g. `Instance ID: essentiaMarco__django_<shortsha>` where `<shortsha>` is the first 8 characters of the base commit.
4. **Format:** `instance_id = owner__repo_` + first 8 chars of base commit (e.g. `essentiaMarco__django_14d026cc`).  
   Note: django-11062 may have a **different** base commit than django-10554 — use the commit that your task/swebench specifies for 11062.
5. **Before pasting the prompt in the new chat:** Replace every `<INSTANCE_ID>` in the prompt with the **actual** value (e.g. `essentiaMarco__django_14d026cc`). The model must see the concrete instance_id string so it can call `load_repo(..., instance_id='essentiaMarco__django_14d026cc')` — do not leave the literal placeholder in the prompt. If the semantic server does not have that instance, `list_repos(include_instances=True)` shows what is available; the branch for 11062 must be indexed so that instance exists.

### Enforcing it in the prompt

The prompt text must **explicitly state** the instance_id to use (e.g. “You MUST use load_repo(..., instance_id='essentiaMarco__django_14d026cc')”) so the model cannot fall back to HEAD or another commit. Without that, the test is not objective — the model might analyze already-fixed or different code.

---

## 6. Short “reminder” prompt (if the model cheats)

If in the new chat the model fetches the PR/commits or loads the repo **without** the required instance_id, paste:

```
Stop. For this task you must NOT fetch the GitHub PR, commits, or any solution from the web. You MUST use load_repo(..., instance_id='<the instance_id for this task>') so you analyze the code at the correct base commit — do not load without instance_id. Use only the bug report and MCP tools to find and fix the bug. Then run the verification tests.
```

---

*This runbook defines an objective test: no solution lookup, MCP-only analysis, and verification by running the Django tests above.*
