# Proposals to Fix "Failed to get session command" (Daytona)

Three levels: **config** (no code), **patch Harbor** (local fix), **upstream / operational**.

---

## 1. Config: Shorten agent timeout (do this first)

So the run finishes **before** Daytona might expire the session (~28–30 min in your case).

**Option A – Override in the job config**

In `job_config_single_10554.yaml` (and optionally `job_config.yaml`), set an agent timeout override, e.g. **20 minutes**:

```yaml
agents:
  - import_path: swebench.rubberduck_agent:RubberDuckClaudeCode
    model_name: anthropic/claude-sonnet-4-6
    override_timeout_sec: 1200   # 20 min
```

The task’s default is 3000 s (50 min). 1200 s is enough for many single-task runs and reduces the chance of hitting a session/command limit.

**Option B – CLI**

```bash
harbor run -c swebench/job_config_single_10554.yaml \
  --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN \
  --agent-timeout 1200
```

**Effect:** Same run, but Harbor stops the agent after 20 min. If the agent would have needed longer, you trade “incomplete” for “no DaytonaError at 28 min.” For django-10554 with a known one-line fix, 20 min is usually enough.

---

## 2. Patch Harbor: More retries and backoff for `get_session_command`

When the Daytona API fails once (transient error), Harbor currently retries only **3 times** with short backoff, then raises. Increasing attempts and wait helps with brief API glitches.

**Apply the patch** (run from the directory that contains `harbor`):

```bash
cd "$(python3 -c "import harbor; print(harbor.__path__[0])")"
# Or, for uv tool install:
# cd ~/.local/share/uv/tools/harbor/lib/python3.13/site-packages/harbor

patch -p0 < /Users/marcomarinucci/repos/rubberduck-demo/swebench/patches/harbor-daytona-more-retries.patch
```

**What the patch does:**

- Imports `DaytonaError`.
- For `_get_session_command_with_retry`: retry only on `DaytonaError`, **10 attempts** (was 3), **exponential backoff** with `min=2, max=30` seconds (was `min=1, max=10`).
- Same for `_get_session_command_logs_with_retry` so log fetch is more resilient too.

**Revert:**

```bash
cd "$(python3 -c "import harbor; print(harbor.__path__[0])")"
patch -p0 -R < /path/to/rubberduck-demo/swebench/patches/harbor-daytona-more-retries.patch
```

**Note:** Re-applying the Harbor tool (e.g. `uv tool install harbor-bench`) will overwrite the patch; re-apply after upgrades if you still need it.

---

## 3. Upstream / operational

| Action | Who | What |
|--------|-----|------|
| **Raise issue / PR to Harbor** | You or maintainers | Propose the same retry/backoff change in `harbor/environments/daytona.py` (and optionally retry only on `DaytonaError`). |
| **Ask Daytona** | You | Confirm session/command lifetime and limits; whether 30+ min runs are supported and how long command results are kept. |
| **Use another environment** | You | If Harbor supports SWE-bench with **Modal** or **local Docker**, run the same task there to avoid Daytona session limits. |

---

## Recommended order

1. **Add `override_timeout_sec: 1200`** (or `--agent-timeout 1200`) so runs finish in 20 min.
2. **Retry** the single-task run; if it still fails with DaytonaError, **apply the Harbor patch** and retry.
3. If it keeps failing, **check Daytona** docs/support and consider **another environment** if available.
