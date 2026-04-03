# Rubberduck MCP Tools — Comprehensive Guide

A practical, experience-based guide for AI agents using the Rubberduck code analysis platform. Written from real usage across multiple coding sessions involving a 22,000-file forensic investigation platform.

---

## What Rubberduck Actually Is

Rubberduck is a code analysis platform delivered as two MCP (Model Context Protocol) servers. Together they let an AI agent do things that are normally impossible with just file reads and text searches:

- Trace how data flows through a program (not just where a variable name appears, but where its *value* comes from and goes to)
- Map every function that would be affected if you changed one line of code
- Detect security vulnerabilities by following user input from entry point to dangerous operation
- Compare two versions of code and report what *semantically* changed (not just text diffs)
- Score an entire repository's health and flag architectural problems

The two servers complement each other:

| | Codebase Intelligence | Semantic Intelligence |
|---|---|---|
| **Scope** | Entire repositories | Individual files/modules |
| **Speed** | Minutes (first run), instant (cached) | Seconds per file |
| **Depth** | Metrics, scores, grades | Line-by-line code graphs |
| **Best for** | "Is this repo healthy?" | "What breaks if I change this function?" |
| **Language** | Python (primary) | Python only |

---

## Codebase Intelligence — The Repository Scanner

### What it does in plain terms
Takes a GitHub repository (or locally indexed project), clones it, and runs 20+ automated checks. Think of it as a code quality report card — it gives you letter grades, identifies security issues, and tells you which files are the most complex or risky.

### When it shines

**1. First contact with an unfamiliar repo**
Before diving into code, run a quick scan to understand what you're working with:
```
analyze_repository(repo="django/django")
```
Returns: file counts, lines of code, average complexity, documentation coverage, coupling score, composite grade (A-F), and AI-generated improvement suggestions. This takes 5-30 seconds on cached repos.

**2. Security auditing**
Find vulnerabilities without reading every file:
```
get_security_report(repo="owner/repo")
```
This catches things grep can't: **taint flow paths** (where user input travels from an HTTP request parameter through function calls until it reaches a SQL query or `eval()` call), hardcoded secrets, weak cryptographic choices, and unsafe deserialization.

*What is a taint flow?* Imagine a user types something into a search box. That string travels through your code — maybe it gets passed to a function, stored in a variable, then eventually used in a database query. If at no point does your code sanitize that string, an attacker could type SQL commands into the search box and corrupt your database. Taint flow analysis traces this entire journey automatically.

**3. Assessing commit risk**
Before or after merging a pull request:
```
get_change_impact(repo="owner/repo", commit="abc123def")
```
Returns a risk score (0-100), which files were touched, how many functions changed, and the "blast radius" — how much of the codebase is affected by this one commit. Particularly useful for code review.

**4. Comparing multiple repositories**
Analyze a batch of repos from a CSV and get cross-repo insights:
```
start_batch_analysis(csv_content="repo,instance_id,base_commit\ndjango/django,run1,HEAD\nflask/flask,run1,HEAD")
→ get_task_status(task_id="...")  # poll until complete
→ download_report(task_id="...")  # CSV with per-repo metrics
→ get_batch_ai_analysis(task_id="...")  # cross-repo insights
```

### The tools, organized by task

**Scanning:**
- `analyze_repository(repo)` — Quick scan: metrics + grade (5-30s)
- `analyze_repository_detailed(repo)` — Deep scan: security + structure + trends (1-10 min)
- `get_security_report(repo)` — Security-only: vulnerabilities + taint flows (1-10 min)
- `get_change_impact(repo, commit)` — Single commit: risk score + blast radius

**Indexing (for performance):**
- `preindex_repository(repo)` — Cache a repo in the background for instant future scans
- `get_index_status(repo)` — Check if indexing is done
- `list_indexed_repos()` — See all cached repos
- `invalidate_index(repo)` — Force re-analysis (e.g., after new commits)

**Batch processing:**
- `start_batch_analysis(csv_content/url/path)` — Analyze many repos at once
- `get_task_status(task_id)` — Check progress
- `download_report(task_id)` — Get CSV results
- `get_batch_ai_analysis(task_id)` — AI insights across the batch

**Setup & admin:**
- `setup_github_app(repo)` — Check if the GitHub App is installed (required for private repos)
- `check_health()` — Verify the server is running
- `get_visualization_url(instance_id)` — Get a browser-viewable dashboard URL

### Practical tips
- **Always call `setup_github_app` first** if analysis fails or times out on a new repo. The CodeAnalyzer GitHub App must be installed for repository access.
- **Use `preindex_repository` proactively** if you know you'll analyze a repo multiple times. First analysis takes minutes; cached analysis returns in under a second.
- **Quick scan is usually enough** for planning. Only use `analyze_repository_detailed` when you specifically need security analysis, historical trends, or structural metrics.
- **For local projects**, use `repo="local/project-name"` format (discovered via `list_indexed_repos`).

---

## Semantic Intelligence — The Code Microscope

This is the more powerful and nuanced server. While Codebase Intelligence gives you a bird's-eye view, Semantic Intelligence lets you look at individual functions under a microscope.

### What it builds (and why it matters)

When you load a Python file, Rubberduck constructs four layers of analysis:

1. **AST (Abstract Syntax Tree)** — The grammatical structure of your code. Every class, function, variable, and statement as a tree. This is what lets the tool list all functions with their line numbers.

2. **CFG (Control Flow Graph)** — Every possible path execution could take through your code. If-statements create branches, loops create cycles, try/except creates alternate paths. This is what lets the tool answer "what conditions must be true for line 42 to execute?"

3. **DDG (Data Dependency Graph)** — How values flow between variables. If `x = a + b`, then `x` depends on `a` and `b`. This is what lets the tool trace a variable from where it's created to everywhere it's used — crucial for security analysis and bug hunting.

4. **Structural graph** — How classes and functions relate to each other. Inheritance, composition, coupling. This is what lets the tool assess blast radius of changes.

*Why does this matter?* A simple text search for `password` finds every file containing that word. But DDG analysis finds every place where the *value* of a password variable travels — even if it gets renamed along the way, passed as a function argument, or stored in a different variable. That's the difference between searching and understanding.

### When it shines

**1. Understanding unfamiliar code fast**

Instead of reading files top-to-bottom, load a module and ask questions:

```
load_repo(repo="local/my-project", subpath="src/auth")
→ symbols_overview(analysis_id="auth_module")
  # Returns: class AuthService (line 15), def login (line 22), def verify_token (line 58)...

→ read_source(analysis_id="auth_module", function_name="login")
  # Returns: the actual source code of the login function

→ query_action(action="call_chain", analysis_id="auth_module", method="login")
  # Returns: login is called by: handle_request (line 10), api_login (line 45)
  #          login calls: verify_password (line 30), create_session (line 35)
```

In three calls, you know the structure, the code, and the dependency chain. Without Rubberduck, you'd need to grep for function names, read multiple files, and manually trace imports.

**2. Safe refactoring — knowing what breaks before you break it**

`plan_change` is one of the most valuable tools. Before modifying code, it tells you the risk:

```
plan_change(
  description="Change the authenticate() function to use JWT instead of session tokens",
  analysis_id="auth_module"
)
```

Returns:
- **Risk level**: medium
- **Affected functions**: authenticate, create_session, verify_token, logout
- **Dependency graph** (as a Mermaid diagram you can visualize)
- **Recommended change order**: "Modify verify_token first (leaf node), then authenticate, then create_session"
- **Test focus areas**: "Test authenticate with expired tokens, verify_token with malformed JWT"

This is where Rubberduck genuinely outperforms manual analysis. In a large codebase, a human developer might miss that `logout()` depends on the session format that `authenticate()` produces. Rubberduck's graph catches it automatically.

**3. Security auditing at the code level**

```
security_audit(analysis_id="api_handlers")
```

Runs actual analysis (not just instructions) and returns structured findings:
- SQL injection: `user_input` flows from `request.args["q"]` → `query_builder()` → `cursor.execute()` without sanitization
- Command injection: `filename` parameter passed to `os.system()` on line 45
- Hardcoded secret: API key literal on line 12

It can also compare sibling function calls to detect anomalies:
```
query_action(action="compare_calls", analysis_id="db_module", func_name="execute")
```
If 9 out of 10 calls to `execute()` use parameterized queries but one uses string formatting, that's flagged as an argument anomaly — a strong indicator of SQL injection.

**4. Bug investigation with runtime evidence**

When you have a Python traceback from a crash:

```
# Step 1: Load the code that crashed
load_repo(repo="local/my-app", subpath="src/core")

# Step 2: Feed the traceback
ingest_runtime_artifact(
  analysis_id="core",
  artifact_type="traceback",
  content="Traceback (most recent call last):\n  File 'handler.py', line 42..."
)

# Step 3: Map the crash to code structure
link_runtime_evidence(analysis_id="core", artifact_id="...")

# Step 4: Rank likely root causes
rank_root_causes(analysis_id="core", artifact_id="...")
# Returns: ranked hypotheses with confidence scores

# Step 5: Get a fix suggestion
propose_minimal_patch(analysis_id="core", root_cause_id="rc_1")

# Step 6: Generate a regression test
generate_regression_test(analysis_id="core", root_cause_id="rc_1")
```

This pipeline goes from "it crashed" to "here's a patch and a test" using both the static code structure and the runtime evidence. The `rank_root_causes` step is particularly valuable — it combines what the code *could* do (static analysis) with what it *actually did* (runtime trace) to prioritize hypotheses.

**5. Semantic diff — understanding what really changed**

Text diffs show you which lines changed. Semantic diffs show you what those changes *mean*:

```
load_code(file_path="old_version.py", analysis_id="before")
load_code(file_path="new_version.py", analysis_id="after")
compare_snapshots(analysis_id_before="before", analysis_id_after="after")
```

Returns:
- Functions added, removed, or modified (with line count changes)
- Variables added or removed
- Call graph edges added or removed (new dependencies or broken ones)
- Risk level: none/low/medium/high based on total changes

This is invaluable for code review. A 200-line diff might look intimidating, but the semantic diff might reveal "one function was refactored, two variables were renamed, and one new dependency was added" — much more actionable.

### The tools, organized by task

**Loading code (always do this first):**
- `list_repos()` — Find available projects
- `load_repo(repo, subpath, max_files)` — Load files from a project
- `load_code(file_path)` — Load a single file (server-accessible paths only)
- `load_code(code="...")` — Load raw source from a string
- `find_files(directory, symbol="func_name")` — Search for files by symbol name (AST-based, not text)
- `list_loaded()` — See what's in analysis memory

**Exploring code structure:**
- `symbols_overview(analysis_id)` — List all classes/functions with line numbers
- `read_source(analysis_id, function_name)` — Read a function's full source
- `read_source(analysis_id, around_line=42, radius=25)` — Read code around a specific line
- `search_code(pattern="regex", analysis_id="all")` — Text search across all loaded files

**Querying code relationships (the 12 analysis actions):**
- `trace_variable` — Follow a variable's value through the code (data flow)
- `call_chain` — Find what calls a function, and what it calls
- `control_guards` — What if/try conditions protect a specific line
- `def_sites` — Where a variable is defined (assigned, imported, or declared as parameter)
- `reaching_defs` — All definitions that could affect a specific line
- `shared_variables` — Variables shared between two functions (coupling detection)
- `compare_calls` — Find anomalous function call patterns (e.g., one call missing a parameter that all others include)
- `search_vertex` — Search the code graph by node name/type
- `search_edge` — Search relationships by type
- `ast_window` — Get the AST around a specific line
- `lsp_query` — Cross-file references and type inference (when Jedi is available)
- `symbols_overview` — Structure listing (also an action)

**High-level analysis:**
- `analyze_code(statement="natural language question")` — Ask about code in plain English
- `plan_change(description="what you want to change")` — Risk assessment + blast radius + recommended order
- `security_audit(analysis_id)` — Structured security findings with evidence chains
- `compare_snapshots(before, after)` — Semantic diff between two code versions
- `export_graph_metrics(analysis_id)` — Raw graph statistics for integration with other tools
- `get_evidence_pack(actions=[...])` — Run multiple queries and combine into a structured report

**Workflows (return step-by-step instructions for you to follow):**
- `understand_code(focus="authentication")` — Guided exploration workflow
- `review_code(diff_or_description="...")` — Code review workflow
- `plan_new_feature(feature_description="...")` — Feature planning with tests-first approach
- `localize_and_fix_bug(traceback="...")` — Bug investigation workflow
- `check_code_logic(function_name="...", concern="null handling")` — Logic correctness workflow
- `check_code_propagation(function_name="...", change_description="...")` — Change impact workflow
- `check_code_changes(changed_functions="...", change_summary="...")` — Quick change review
- `compare_code_versions(focus="database layer")` — Version comparison workflow
- `codebase_audit(audit_type="security")` — Security or quality audit workflow
- `generate_coherent_code(what_to_implement="...")` — Code generation aligned with codebase style
- `runtime_debug_and_fix(artifact_type="traceback")` — Runtime debugging pipeline

**Runtime intelligence (for production debugging):**
- `ingest_runtime_artifact(artifact_type, content)` — Parse tracebacks/logs into structured events
- `link_runtime_evidence(analysis_id, artifact_id)` — Map runtime events to code graph nodes
- `runtime_timeline(analysis_id, artifact_id)` — Causal timeline around a failure
- `rank_root_causes(analysis_id)` — Weighted root cause ranking
- `propose_minimal_patch(root_cause_id)` — Generate fix candidates
- `select_patch_candidate` / `render_patch_diff` / `apply_patch_candidate` — Patch workflow
- `generate_regression_test(root_cause_id)` — Auto-generate a test for the fix
- `verify_fix(before, after)` — Confirm fix doesn't introduce regressions

### Practical tips from real usage

**Always scope your loads.** `load_repo` with no `subpath` loads from the repo root. For a large project, this is slow and wastes memory. Always scope: `load_repo(repo="local/myapp", subpath="backend/src/myapp/auth", max_files=10)`.

**`symbols_overview` before anything else.** After loading, this is your table of contents. It shows every class and function with line numbers so you know what to query next.

**Use `query_action` for precision, `analyze_code` for exploration.** Natural language queries via `analyze_code` are convenient but sometimes fuzzy-match to wrong variables. When you need an exact answer ("what calls `authenticate`?"), use `query_action(action="call_chain", method="authenticate")` directly.

**`search_code` with `analysis_id="all"` is your cross-file grep.** It searches the actual loaded source text, not the graph. Use it for string literals, comments, imports, and patterns that aren't captured in the graph.

**Workflow tools don't execute — they instruct.** `review_code()` returns a list of steps like "Step 1: call read_source... Step 2: call call_chain..." You must follow these steps yourself. Analysis tools like `plan_change()` and `security_audit()` return actual results.

**Load both versions for semantic diff.** `compare_snapshots` needs two analysis IDs. Load the old code as `analysis_id="before"` and new code as `analysis_id="after"`, then compare.

**The `plan_change` tool is the single most useful tool for safe code modification.** Call it before any non-trivial change. The risk assessment, dependency graph, and recommended change order have consistently caught issues that manual analysis missed.

---

## Putting Them Together

The two servers are most powerful when combined. Here's a real example from a session where we were debugging a background job that was stuck at 75%:

```
# Step 1: Quick repo health check (Codebase Intelligence)
analyze_repository(repo="local/rubberduck-demo")
→ Overall grade: B+, 74 Python files, complexity within bounds

# Step 2: Load the specific module (Semantic Intelligence)
load_repo(repo="local/rubberduck-demo", subpath="backend/src/rubberduck/jobs")
load_repo(repo="local/rubberduck-demo", subpath="backend/src/rubberduck/graph")

# Step 3: Understand the job manager structure
symbols_overview(analysis_id="manager")
→ JobManager class: submit(), _wrapper(), update_progress(), cancel()

# Step 4: Read the wrapper function that runs background jobs
read_source(analysis_id="manager", function_name="_wrapper")
→ Full source of the thread execution wrapper

# Step 5: Trace the call chain — what does the stuck job call?
query_action(action="call_chain", analysis_id="manager", method="_wrapper")
→ _wrapper calls: callable_fn, commit, broadcast, error

# Step 6: Check the relationship extraction code for logic issues
check_code_logic(analysis_id="builder", function_name="build_graph",
                 concern="performance with large datasets")
→ Identified: self-join on entity_mentions is O(n^2) per file

# Step 7: Security check on the module
search_code(pattern="exec\\(|eval\\(|subprocess|shell=True", analysis_id="all")
→ No dangerous patterns found
```

This combination — repository-level health from Codebase Intelligence plus function-level tracing from Semantic Intelligence — found the root cause (a quadratic SQL self-join on 3.2M rows) in minutes, where manual debugging would have taken much longer.

---

## Quick Reference: Which Tool For Which Question

| Question | Tool | Server |
|---|---|---|
| "Is this repo healthy?" | `analyze_repository` | Codebase |
| "Any security vulnerabilities?" | `get_security_report` OR `security_audit` | Both |
| "How risky is this commit?" | `get_change_impact` | Codebase |
| "What functions are in this file?" | `symbols_overview` | Semantic |
| "Show me this function's code" | `read_source` | Semantic |
| "What calls this function?" | `query_action(call_chain)` | Semantic |
| "Where does this variable come from?" | `query_action(trace_variable)` | Semantic |
| "What breaks if I change this?" | `plan_change` | Semantic |
| "What really changed between these versions?" | `compare_snapshots` | Semantic |
| "The app crashed with this traceback" | `ingest_runtime_artifact` → `rank_root_causes` | Semantic |
| "Find the bug in this function" | `check_code_logic` | Semantic |
| "Review this code change" | `review_code` | Semantic |
| "How should I add this feature?" | `plan_new_feature` | Semantic |
| "Is this pattern used consistently?" | `query_action(compare_calls)` | Semantic |
| "What conditions guard this line?" | `query_action(control_guards)` | Semantic |

---

## Known Limitations (Observed in Practice)

1. **Python only for Semantic Intelligence.** The code graph analysis only works on `.py` files. JavaScript, TypeScript, Go, etc. are not supported for deep analysis.

2. **Remote server can't access local files directly.** `load_code(file_path="/local/path")` fails with "Access denied" if the file is on your machine, not the server. Use `load_repo` with indexed projects, or pass code as a string.

3. **Fuzzy matching can misfire.** When `analyze_code` can't find a variable you asked about, it silently substitutes the closest match. You'll see warnings like `⚠ 'my_var' not in analysis — partial match to 'v'`. Use `query_action` with exact names when this happens.

4. **Workflow tools return instructions, not results.** `review_code`, `plan_new_feature`, `understand_code` etc. return a list of steps for you to execute. They don't run the analysis themselves. The analysis tools (`plan_change`, `security_audit`, `analyze_code`, `query_action`) return actual results.

5. **Index can be stale.** If files were added or modified after the last index, the MCP won't see them. For Codebase Intelligence: `invalidate_index` then `preindex_repository`. For Semantic Intelligence: just `load_repo` again (it reads from disk each time).

6. **Memory limits with large loads.** Loading too many files (>15-20) in Semantic Intelligence can be slow. Always scope with `subpath` and keep `max_files` reasonable.

7. **Cross-file analysis is limited.** Semantic Intelligence analyzes files independently. It can't trace a function call from file A into file B unless both are loaded and you use `lsp_query` (which requires Jedi and `repo_path`). For cross-file tracing, load all relevant files in the same session.
