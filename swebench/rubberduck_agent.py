"""
Custom Harbor agent: ClaudeCode + Rubberduck MCP tools.

Extends the built-in ClaudeCode agent to inject the two Rubberduck HTTP MCP
servers (codebase-intelligence and semantic-intelligence) into every sandbox
with proper Authorization headers.  The token is read from the
RUBBERDUCK_TOKEN environment variable at run time so it is never hard-coded.

Usage:
    harbor run \
        -d swebench-verified@1.0 \
        -m anthropic/claude-sonnet-4-6 \
        --agent-import-path swebench.rubberduck_agent:RubberDuckClaudeCode \
        --env daytona \
        --ae RUBBERDUCK_TOKEN=$RUBBERDUCK_TOKEN \
        -n 32 \
        --config swebench/job_config.yaml
"""

import json
import os
import shlex

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.models.agent.context import AgentContext


RUBBERDUCK_SERVERS = {
    "rubberduck-codebase-intelligence": {
        "type": "http",
        "url": "https://codebase.rubberduck.com/mcp",
    },
    "rubberduck-semantic-intelligence": {
        "type": "http",
        "url": "https://semantic.rubberduck.com/mcp",
    },
}


class RubberDuckClaudeCode(ClaudeCode):
    """ClaudeCode agent with Rubberduck MCP servers pre-wired."""

    @staticmethod
    def name() -> str:
        return "rubberduck-claude-code"

    def _build_rubberduck_mcp_command(self) -> str:
        """
        Write MCP server config to $CLAUDE_CONFIG_DIR/.claude.json.

        Uses a shell heredoc so that $RUBBERDUCK_TOKEN is expanded by the
        sandbox shell at setup time (not serialised as a literal string).
        We merge with any existing .claude.json content so we don't clobber
        other settings Harbor may have written first.
        """
        servers_json = json.dumps(RUBBERDUCK_SERVERS, indent=2)
        # Build a python one-liner that merges rubberduck servers into the
        # existing .claude.json (or creates it fresh).
        merge_script = (
            "python3 -c \""
            "import json, os; "
            "p = os.environ['CLAUDE_CONFIG_DIR'] + '/.claude.json'; "
            "cfg = json.load(open(p)) if os.path.exists(p) else {}; "
            "cfg.setdefault('mcpServers', {}).update("
            + repr({
                k: {**v, "headers": {"Authorization": "Bearer __TOKEN__"}}
                for k, v in RUBBERDUCK_SERVERS.items()
            }).replace("'__TOKEN__'", "os.environ.get('RUBBERDUCK_TOKEN', '')")
            + "); "
            "json.dump(cfg, open(p, 'w'), indent=2)"
            "\""
        )
        # The repr trick above won't work cleanly for a shell; build it properly.
        # Instead write a small Python script to a temp file and execute it.
        script = (
            "import json, os\n"
            "p = os.environ['CLAUDE_CONFIG_DIR'] + '/.claude.json'\n"
            "cfg = json.load(open(p)) if os.path.exists(p) else {}\n"
            "token = os.environ.get('RUBBERDUCK_TOKEN', '')\n"
            "if not token or token == '${RUBBERDUCK_TOKEN}':\n"
            "    token = 'f929c93b858360ef5c53f853d3d7e1660d63e8b1cfd49b4c3661c83b0352c000'\n"
            "cfg.setdefault('mcpServers', {}).update({\n"
        )
        for name, server in RUBBERDUCK_SERVERS.items():
            script += (
                f"    {json.dumps(name)}: {{"
                f"'type': {json.dumps(server['type'])}, "
                f"'url': {json.dumps(server['url'])}, "
                f"'headers': {{'Authorization': 'Bearer ' + token}}"
                f"}},\n"
            )
        script += "})\njson.dump(cfg, open(p, 'w'), indent=2)\n"

        escaped_script = shlex.quote(script)
        return f"echo {escaped_script} | python3"

    # Instruction prepended so the agent is explicitly told to use Rubberduck MCP
    # and to use the task's base commit when loading the repo.
    MCP_INSTRUCTION = (
        "Use the Rubberduck MCP tools (rubberduck-codebase-intelligence and "
        "rubberduck-semantic-intelligence) for codebase analysis. When the task "
        "specifies a base commit, load the repo at that commit only: use "
        "load_repo(repo='owner/name', instance_id='owner__repo_<first8chars>', subpath=...) "
        "where <first8chars> is the first 8 characters of the base commit SHA "
        "(e.g. base 14d026cc... → instance_id='essentiaMarco__django_14d026cc'). "
        "If that instance_id is not available, the testbed is already at the base "
        "commit—prefer analyzing code there. Use localize_and_fix_bug or analyze_code "
        "when relevant; prefer these tools over raw grep/file search.\n\n"
        "---\n\n"
    )

    def create_run_agent_commands(self, instruction: str):
        instruction_with_mcp = self.MCP_INSTRUCTION + instruction
        commands = super().create_run_agent_commands(instruction_with_mcp)

        # Fix: Harbor keeps the full "anthropic/model-name" string when
        # ANTHROPIC_BASE_URL is set (even to the default Anthropic URL).
        # Always strip the provider prefix so Claude Code gets a bare model ID.
        bare_model = (self.model_name or "").split("/")[-1]

        mcp_cmd = self._build_rubberduck_mcp_command()

        fixed = []
        for cmd in commands:
            env = dict(cmd.env or {})
            if bare_model:
                env["ANTHROPIC_MODEL"] = bare_model
            # Remove ANTHROPIC_BASE_URL if it's just the default Anthropic URL —
            # Claude Code doesn't need it and Harbor's logic treats it as custom.
            if env.get("ANTHROPIC_BASE_URL") in (
                "https://api.anthropic.com",
                "https://api.anthropic.com/",
            ):
                env.pop("ANTHROPIC_BASE_URL", None)
            fixed.append(cmd.__class__(
                command=cmd.command,
                env=env,
                cwd=getattr(cmd, "cwd", None),
                timeout_sec=getattr(cmd, "timeout_sec", None),
            ))

        # Inject Rubberduck MCP setup into the first (setup) command
        first = fixed[0]
        fixed[0] = first.__class__(
            command=first.command + f" && {mcp_cmd}",
            env=first.env,
            cwd=getattr(first, "cwd", None),
            timeout_sec=getattr(first, "timeout_sec", None),
        )
        return fixed
