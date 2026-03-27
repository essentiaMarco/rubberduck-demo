# Right Settings, Typical Run Times, and What Others Do

Summary from public docs and common practice (SWE-bench, Harbor, Daytona).

---

## 1. SWE-bench: timeouts and run times

### Per-instance timeout

- The **evaluation harness** has a `--timeout` (seconds) for **evaluating each instance** (patch apply + run tests).
- Common guidance: **300–600 seconds (5–10 min)** per instance for the **verification** step (running tests).
- The **agent** (time to produce the patch) is separate and often allowed **longer** (e.g. 10–30+ min per task in configs).

### Full-benchmark run times

| Setup | What | Typical time |
|-------|------|----------------|
| **SWE-bench Verified (500 tasks)** | Single machine, 32 cores, 128 GB RAM, **prebuilt Docker images** | **~62 minutes** total (Epoch AI / bayes.net) |
| **SWE-bench Lite (300 tasks)** | 16 cores, `max_workers=12`, cache_level=env | **~30 min** total |
| **SWE-bench Lite (300 tasks)** | 8 cores, `max_workers=6`, cache_level=env | **~50 min** total |
| **SWE-bench Lite** | With instance-level cache | **~15 min** total |

So **per task** when heavily parallelized is on the order of **tens of seconds to a few minutes** (evaluation only). When you run **one task end-to-end** (agent + verification), **10–25 minutes** per task is a reasonable ballpark.

### What people do

- Use **prebuilt / cached images** when possible to avoid long build times.
- Run **many instances in parallel** (`max_workers`, multiple trials) so total wall-clock time is dominated by the slowest instance, not the sum of all.
- Set a **per-instance timeout** so one stuck task doesn’t block the whole run (often in the **5–10 min** range for verification, and **10–30 min** for agent time depending on benchmark and harness).

---

## 2. Harbor and task config

- **Agent timeout** is set per task (e.g. in dataset `task.toml`) and can be overridden in the job or via CLI (`--agent-timeout`, `override_timeout_sec`).
- **Default** in Harbor’s task config is **600 s (10 min)** for agent and verifier unless the dataset overrides it (e.g. SWE-bench Verified tasks often use **3000 s = 50 min**).
- **Timeout multiplier** scales all timeouts (agent, verifier, setup, build).

**Practical recommendation:** For single-task or small runs on remote sandboxes (e.g. Daytona), cap agent time so runs finish before platform/session limits (e.g. **20 min = 1200 s**). That’s enough for many tasks and avoids late timeouts or “Failed to get session command” near the 28–30 min mark.

---

## 3. Daytona: limits and settings

### Sandbox lifecycle (from Daytona docs)

- **Auto-stop:** Sandboxes can **auto-stop after a period of inactivity**. Default in the platform is **15 minutes** of inactivity unless overridden.
- **Harbor** creates Daytona sandboxes with **`auto_stop_interval_mins=0`** by default (no auto-stop), so the 28 min failure is unlikely to be this specific timer.
- **Creation timeout:** Sandbox creation has a timeout (default 60 s in docs); **0** means no timeout.
- **Command execution:** Can pass a **timeout** (seconds); **0** means wait indefinitely.

### Rate limits

- **429** responses when limits are hit (per tier: general, sandbox creation, lifecycle).
- **Best practice (Daytona):** On 429, **retry with exponential backoff**; use **Retry-After** header when present.

### Resource tiers

- Tier 1: 10 vCPU / 10 GiB RAM / 30 GiB storage (email verified).
- Higher tiers give more sandboxes and higher rate limits.

### What this means for your run

- No explicit “session TTL” or “command result TTL” in the public docs; the **“Failed to get session command”** after ~28 min may be backend cleanup, a transient API error, or an undocumented limit.
- Keeping **agent runs under ~20–25 minutes** and **retrying on DaytonaError** (as in the Harbor patch) aligns with “right settings” and “what others do”: bounded run time + resilient polling.

---

## 4. Recommended settings for your setup

| Setting | Suggested value | Reason |
|--------|------------------|--------|
| **Agent timeout** | **1200 s (20 min)** | Finish before ~28–30 min issues; enough for many single-task runs. |
| **Verifier timeout** | Keep dataset default (e.g. 3000 s) or 600–1200 s | Verification is usually 5–15 min per task. |
| **Harbor retries for `get_session_command`** | **10 attempts**, backoff **2–30 s**, only on **DaytonaError** | Handles transient API/backend errors (see `patches/harbor-daytona-more-retries.patch`). |
| **Concurrency** | **1** for single-task validation; **4–8** for batch | Matches “one task at a time” vs “parallel trials.” |

**Single-task run (django-10554):**

- **Typical duration:** About **10–20 minutes** end-to-end (setup + agent + verifier).
- **Config:** `job_config_single_10554.yaml` with `override_timeout_sec: 1200` (already set).

**Full 26-task Django job:**

- **Typical duration:** Depends on concurrency; with 8 parallel trials, total wall time is on the order of **1–2 hours** if most tasks finish within the agent timeout.
- Use the same **20 min** agent cap if you want to avoid late Daytona errors; increase only if you need longer for harder tasks and accept a higher risk of session/command issues.

---

## 5. References

- SWE-bench harness: [The Harness - SWE-bench](https://www.swebench.com/SWE-bench/reference/harness/) (`--timeout`, `--max_workers`, cache levels).
- Run SWE-bench Verified in ~62 min: [bayes.net/swebench-docker](https://bayes.net/swebench-docker/), [epoch.ai blog](http://epoch.ai/blog/swebench-docker) (32 cores, prebuilt images).
- Daytona: [Limits](https://daytona.io/docs/en/limits/), [Sandbox (Python SDK)](https://www.daytona.io/docs/en/python-sdk/sync/sandbox/) (auto_stop_interval, timeouts), [Process](https://www.daytona.io/docs/python-sdk/process/) (exec timeout).
- Harbor: task config defaults (e.g. `harbor/models/task/config.py`), Daytona env (`auto_stop_interval_mins=0`, retries).
