"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.
Uses Arcade MCP Gateway for Linear + GitHub + Slack integration.
"""

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Literal, TypedDict, cast

from dotenv import load_dotenv

load_dotenv()

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, McpServerConfig
from claude_agent_sdk.types import HookCallback, HookMatcher

# WORKAROUND: The SDK's Windows command line length limit (8000 chars) triggers a
# fallback that writes agents JSON to a temp file using @filepath syntax. However,
# the Claude CLI does not support @filepath for --agents, so custom agents are
# silently dropped. We use stub prompts (see agents/definitions.py) to keep the
# command line under Windows' ~32768 OS limit, but still raise the SDK limit to
# prevent the broken @filepath fallback from activating.
# See: claude_agent_sdk/_internal/transport/subprocess_cli.py line 37
import claude_agent_sdk._internal.transport.subprocess_cli as _subprocess_cli
_subprocess_cli._CMD_LENGTH_LIMIT = 100000  # Prevent broken @filepath fallback

from arcade_config import (
    ALL_ARCADE_TOOLS,
    ARCADE_TOOLS_PERMISSION,
    get_arcade_mcp_config,
    validate_arcade_config,
)
from agents.definitions import AGENT_PROMPT_FILES, create_agent_definitions
from security import bash_security_hook


# Valid permission modes for the Claude SDK
PermissionMode = Literal["acceptEdits", "acceptAll", "reject", "ask"]


class SandboxConfig(TypedDict):
    """Sandbox configuration for bash command isolation."""

    enabled: bool
    autoAllowBashIfSandboxed: bool


class PermissionsConfig(TypedDict):
    """Permissions configuration for file and tool operations."""

    defaultMode: PermissionMode
    allow: list[str]


class SecuritySettings(TypedDict):
    """Complete security settings structure."""

    sandbox: SandboxConfig
    permissions: PermissionsConfig


# Playwright MCP tools for browser automation
PLAYWRIGHT_TOOLS: list[str] = [
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_close",
]

# Built-in tools
BUILTIN_TOOLS: list[str] = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]

# Prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_orchestrator_prompt() -> str:
    """Load the orchestrator system prompt."""
    return (PROMPTS_DIR / "orchestrator_prompt.md").read_text(encoding="utf-8")


def copy_agent_prompts_to_project(project_dir: Path) -> Path:
    """Copy agent prompt files into the project's .prompts/ directory.

    Agents use stub prompts that reference these files. This keeps the CLI
    command line short (under Windows' ~32768 char limit) while giving agents
    access to their full instructions within the sandbox.

    Returns:
        Path to the .prompts/ directory
    """
    prompts_dest = project_dir / ".prompts"
    prompts_dest.mkdir(parents=True, exist_ok=True)

    for filename in AGENT_PROMPT_FILES.values():
        src = PROMPTS_DIR / filename
        dst = prompts_dest / filename
        shutil.copy2(src, dst)

    # Copy kill_port utility for mid-session port cleanup
    kill_port_src = Path(__file__).parent / "kill_port.py"
    if kill_port_src.exists():
        shutil.copy2(kill_port_src, project_dir / "kill_port.py")

    return prompts_dest


def create_security_settings() -> SecuritySettings:
    """
    Create the security settings structure.

    Returns:
        SecuritySettings with sandbox and permissions configured
    """
    return SecuritySettings(
        sandbox=SandboxConfig(enabled=True, autoAllowBashIfSandboxed=True),
        permissions=PermissionsConfig(
            defaultMode="acceptEdits",
            allow=[
                # Allow all file operations within the project directory
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
                "Glob(./**)",
                "Grep(./**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Playwright MCP tools for browser automation
                *PLAYWRIGHT_TOOLS,
                # Allow all Arcade MCP Gateway tools (Linear + GitHub + Slack)
                ARCADE_TOOLS_PERMISSION,
            ],
        ),
    )


def write_security_settings(project_dir: Path, settings: SecuritySettings) -> Path:
    """
    Write security settings to project directory.

    Args:
        project_dir: Directory to write settings to
        settings: Security settings to write

    Returns:
        Path to the settings file

    Raises:
        IOError: If settings file cannot be written
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    settings_file: Path = project_dir / ".claude_settings.json"

    try:
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError as e:
        raise IOError(
            f"Failed to write security settings to {settings_file}: {e}\n"
            f"Check disk space and file permissions.\n"
            f"Agent cannot start without security settings."
        ) from e

    return settings_file


def create_client(project_dir: Path, model: str) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use

    Returns:
        Configured ClaudeSDKClient

    Raises:
        ValueError: If required environment variables are not set

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
       (bwrap/docker-style isolation)
    2. Permissions - File operations restricted to project_dir only
       (enforced by SDK before tool execution)
    3. Security hooks - Bash commands validated against an allowlist
       (runs pre-execution via PreToolUse hook, see security.py for ALLOWED_COMMANDS)

    Execution: Permissions checked first, then hooks run, finally sandbox executes.
    """
    # Validate Arcade configuration
    validate_arcade_config()

    # Get Arcade MCP configuration
    arcade_config = get_arcade_mcp_config()

    # Copy agent prompt files into project directory for sandbox access
    prompts_dest = copy_agent_prompts_to_project(project_dir)

    # Create and write security settings
    security_settings: SecuritySettings = create_security_settings()
    settings_file: Path = write_security_settings(project_dir, security_settings)

    print(f"Created security settings at {settings_file}")
    print(f"   - Agent prompts copied to: {prompts_dest}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print(f"   - MCP servers: playwright (browser), arcade ({arcade_config['url']})")
    print()

    # Load orchestrator prompt as system prompt
    orchestrator_prompt = load_orchestrator_prompt()

    # Create agent definitions with absolute prompt paths for this project
    agent_definitions = create_agent_definitions(project_dir)

    # Diagnostic: verify agents will be passed correctly to CLI
    agents_dict = {
        name: {k: v for k, v in asdict(agent_def).items() if v is not None}
        for name, agent_def in agent_definitions.items()
    }
    agents_json_len = len(json.dumps(agents_dict))
    print(f"   Agents: {list(agent_definitions.keys())} ({agents_json_len} chars)")
    print(f"   SDK cmd limit (patched): {_subprocess_cli._CMD_LENGTH_LIMIT} chars")
    print()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=orchestrator_prompt,
            allowed_tools=[
                *BUILTIN_TOOLS,
                *PLAYWRIGHT_TOOLS,
                *ALL_ARCADE_TOOLS,
            ],
            mcp_servers=cast(
                dict[str, McpServerConfig],
                {
                    "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
                    "arcade": arcade_config,
                },
            ),
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="Bash",
                        hooks=[cast(HookCallback, bash_security_hook)],
                    ),
                ],
            },
            agents=agent_definitions,
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),
        )
    )
