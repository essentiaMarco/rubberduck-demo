# Why the 16:28 Run Failed (DaytonaError)

This document summarizes the root cause of **`DaytonaError: Failed to get session command:`** for the run in `jobs/2026-03-13__16-28-39`, using the Harbor and Daytona SDK code paths.

---

## 1. What Happened

- **Environment & setup:** Succeeded (sandbox built, agent setup ran).
- **Agent execution:** Ran in the Daytona sandbox for **~28 minutes** (23:29:01 → 23:57:25 UTC).
- **Failure:** When Harbor tried to **fetch the result** of that command from Daytona (poll for exit code and logs), the Daytona API call **`get_session_command(session_id, command_id)`** failed. The error message was empty after the prefix, so the API returned an error with no body/message.
- **Consequence:** Harbor couldn’t get stdout/stderr or exit code, so it couldn’t download agent logs or run the verifier. The trial is reported as **error** (DaytonaError), not as a completed trial with reward 0.

---

## 2. Code Path (Where It Failed)

1. **Trial** (`harbor/trial/trial.py`):  
   `_execute_agent()` wraps `agent.run()` in `asyncio.wait_for(..., timeout=self._agent_timeout_sec)`.  
   For this task, `agent_timeout_sec` is **3000** (50 min) from the dataset `task.toml`, so the run was not killed by Harbor’s timeout.

2. **Daytona environment** (`harbor/environments/daytona.py`):  
   - `exec()` → `_sandbox_exec()` runs the command via `execute_session_command`, then calls **`_poll_response(session_id, response.cmd_id)`** to wait for completion.
   - **`_poll_response`** (lines 872–891): in a loop, calls **`_get_session_command_with_retry(session_id, command_id)`** every 1 second until `response.exit_code is not None`. There is **no inner timeout** in this loop; it can run for the full agent timeout (e.g. 28+ minutes).

3. **Retry wrapper** (`_get_session_command_with_retry`, lines 853–856):  
   Uses `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...))`. So **at most 3 attempts** per poll. It calls **`self._sandbox.process.get_session_command(session_id, command_id)`**.

4. **Daytona SDK** (`daytona/_async/process.py`):  
   `get_session_command` is decorated with `@intercept_errors(message_prefix="Failed to get session command: ")`. It calls **`self._api_client.get_session_command(session_id=..., command_id=...)`**.  
   When the **Daytona API** returns an error (e.g. 404, 500, or connection/backend error), the SDK turns it into **`DaytonaError("Failed to get session command: " + msg)`**. In our case **`msg` was empty**, so the API response had no (or empty) body/message.

5. **Failure moment:** After ~28 minutes of polling every second, one of the **`get_session_command`** calls failed (API error). The retry ran 3 times and all failed → **DaytonaError** was raised out of `_poll_response` → trial failed with **1 error**, **0 trials**.

---

## 3. Root Cause (Why the API Fails)

The installed code doesn’t show why the Daytona **backend** returns an error, but the behavior is consistent with:

1. **Session or command lifecycle on Daytona’s side**  
   After a long run (e.g. 28+ minutes), the backend may:
   - close or expire the session,
   - remove or stop tracking the command,
   - or have a limit on how long command results are retained.  
   Then a later **get_session_command** returns 404 or an error with no message.

2. **Transient backend/API issue**  
   Network blip, backend restart, or rate limiting could cause a one-off failure. With only **3 retries** and exponential backoff, a short outage can still surface as DaytonaError.

3. **Empty error message**  
   The API responded with an error (so the SDK raised), but the response **body** was empty or didn’t contain a `message` field. The Daytona SDK’s `_get_open_api_exception_message()` then leaves the message empty, so you see **"Failed to get session command: "** with nothing after the colon.

---

## 4. Why You Can’t See “Solved” or “Used MCP” for This Run

- **Solved:** The verifier never ran (Harbor never got the command result), so there is no reward and no “solved” outcome for this run.
- **Used Rubberduck MCP:** Agent logs (trajectory, session logs) are downloaded **after** a successful **get_session_command** + **get_session_command_logs**. Because **get_session_command** failed, Harbor reported “Failed to download logs” and didn’t save `trajectory.json` or session details. So there is no local record of tool usage (including MCP) for this run.

---

## 5. What You Can Do

| Action | Purpose |
|--------|--------|
| **Retry the same run** | If the cause was transient, the next run may complete and you’ll get logs + verifier result. |
| **Shorten agent work** | Use a smaller timeout or a task that typically finishes in &lt; 15–20 min so the session is less likely to expire before Harbor gets the result. |
| **Ask Daytona** | Check docs or support for session/command lifetime and limits; confirm whether long-running commands (e.g. 30+ min) are supported and how long results are kept. |
| **Increase retries** | In Harbor’s Daytona layer, increasing the retry count for **get_session_command** could help with transient API errors (would require a local patch or upstream change). |

---

## 6. References (from your install)

- **Harbor:** `.../harbor/environments/daytona.py` (e.g. `_sandbox_exec`, `_poll_response`, `_get_session_command_with_retry`).
- **Daytona SDK:** `.../daytona/_async/process.py` (`get_session_command`), `.../daytona/_utils/errors.py` (`intercept_errors`, `DaytonaError`).
- **Task timeout:** `agent.timeout_sec = 3000` and `verifier.timeout_sec = 3000` in the dataset `task.toml` for `django__django-10554`.
