# Run a clean test (single task, correct commit, MCP)

Use this checklist to run one SWE-bench task (e.g. django-10554) with Rubberduck indexed at the right commit and MCP configured.

---

## 1. Indexing (already done)

You indexed all 26 branches with **rubberduck-codebase-intelligence** `preindex_repository`. For django-10554:

- **Branch:** `swebench/django-10554`
- **Commit:** `14d026cccb144c6877294ba4cd4e03ebf0842498`
- **Instance ID:** `essentiaMarco__django_14d026cc`
- **Status:** READY (Phase 1 + Phase 2)

So the **codebase-intelligence** server has the correct commit cached. The **semantic-intelligence** server may use the same instances (from the same Rubberduck backend); if so, `load_repo(..., instance_id="essentiaMarco__django_14d026cc")` will load that commit. No extra indexing step is required for a clean test.

---

## 2. What “clean” means

- **One task:** django__django-10554 only (single-task config).
- **Correct commit:** Testbed is at base commit 14d026cc; the agent instruction tells the model to use `instance_id="essentiaMarco__django_14d026cc"` when calling semantic MCP so analysis matches the testbed.
- **MCP configured:** Token passed via `--ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN`; agent injects both Rubberduck MCP servers into the sandbox and instructs the model to use them.
- **Enough time:** Agent timeout 25 min (1500 s) so the run can finish without hitting the limit (increase to 30 min in the YAML if needed).

---

## 3. Steps to run the clean test

**1. From the repo root:**

```bash
cd /Users/marcomarinucci/repos/rubberduck-demo
```

**2. Set the token (so `--ae` gets a real value):**

```bash
export RUBBERDUCK_TOKEN='f929c93b858360ef5c53f853d3d7e1660d63e8b1cfd49b4c3661c83b0352c000'
```

**3. Run the single-task job and let it finish (about 15–25 min):**

```bash
harbor run -c swebench/job_config_single_10554.yaml --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN
```

Do not interrupt the run. Wait until Harbor prints the result table and writes `jobs/YYYY-MM-DD__HH-MM-SS/result.json`.

**4. Check the result:**

- **Mean reward 1.0** → task solved (verifier passed).
- **Mean reward 0.0** and **AgentTimeoutError** → increase `override_timeout_sec` in `swebench/job_config_single_10554.yaml` (e.g. to `1800` for 30 min) and rerun.
- **Mean reward 0.0** and **DaytonaError** → see `FAILURE_ANALYSIS_DAYTONA.md` and `FIX_PROPOSALS_DAYTONA.md`; the Harbor patch (more retries) is already applied if you applied it earlier.

**5. (Optional) Confirm MCP usage:**

In the trial folder, open `agent/trajectory.json` and search for `load_repo`, `analyze_code`, or `rubberduck`. If you see those tool calls, the agent used the Rubberduck MCP tools.

---

## 4. Config summary

| Item | Value |
|------|--------|
| Config file | `swebench/job_config_single_10554.yaml` |
| Task | django__django-10554 |
| Agent timeout | 1500 s (25 min) |
| Token | Pass via `--ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN` after `export RUBBERDUCK_TOKEN=...` |

---

## 5. If the agent still times out

Edit `swebench/job_config_single_10554.yaml` and set:

```yaml
override_timeout_sec: 1800   # 30 min
```

Then run the same `harbor run` command again. A single-task run that uses MCP to find the fix and apply it should usually finish in under 25 min; 30 min gives extra margin.
