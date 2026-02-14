"""
Agent Definitions
=================

Specialized agent configurations using Claude Agent SDK's AgentDefinition.
Model selection is configurable via environment variables.
"""

import os
from pathlib import Path
from typing import Final, Literal, TypeGuard

from claude_agent_sdk.types import AgentDefinition

from arcade_config import (
    get_linear_tools,
    get_github_tools,
    get_slack_tools,
    get_coding_tools,
)

# File tools needed by multiple agents
FILE_TOOLS: list[str] = ["Read", "Write", "Edit", "Glob"]

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Valid model options for AgentDefinition
ModelOption = Literal["haiku", "sonnet", "opus", "inherit"]

# Valid model values as a tuple for runtime validation
_VALID_MODELS: Final[tuple[str, ...]] = ("haiku", "sonnet", "opus", "inherit")

# Default models for each agent (immutable)
DEFAULT_MODELS: Final[dict[str, ModelOption]] = {
    "linear": "haiku",
    "coding": "sonnet",
    "github": "haiku",
    "slack": "haiku",
}


def _is_valid_model(value: str) -> TypeGuard[ModelOption]:
    """Type guard to validate model option values."""
    return value in _VALID_MODELS


def _get_model(agent_name: str) -> ModelOption:
    """
    Get the model for an agent from environment variable or default.

    Environment variables:
        LINEAR_AGENT_MODEL, CODING_AGENT_MODEL, GITHUB_AGENT_MODEL, SLACK_AGENT_MODEL

    Valid values: haiku, sonnet, opus, inherit
    """
    env_var = f"{agent_name.upper()}_AGENT_MODEL"
    value = os.environ.get(env_var, "").lower().strip()

    if _is_valid_model(value):
        return value  # Type checker knows this is ModelOption via TypeGuard

    default = DEFAULT_MODELS.get(agent_name)
    if default is not None:
        return default  # DEFAULT_MODELS is typed as dict[str, ModelOption]

    # Fallback for unknown agent names
    return "haiku"


def _load_prompt(name: str) -> str:
    """Load a prompt file."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


# Agent prompt file names (relative to project dir .prompts/)
AGENT_PROMPT_FILES: Final[dict[str, str]] = {
    "linear": "linear_agent_prompt.md",
    "coding": "coding_agent_prompt.md",
    "github": "github_agent_prompt.md",
    "slack": "slack_agent_prompt.md",
}


def _stub_prompt(agent_name: str, project_dir: Path | None = None) -> str:
    """Create a short stub prompt that tells the agent to read its full instructions from a file.

    On Windows, embedding full prompts in AgentDefinition causes the CLI command line
    to exceed the OS ~32768 char limit. Instead, we pass a short stub and the agent
    reads the full prompt from .prompts/ in the project directory.

    Uses absolute path when project_dir is provided to avoid path resolution issues
    in sub-agents that may not share the orchestrator's working directory.
    """
    filename = AGENT_PROMPT_FILES[agent_name]
    if project_dir is not None:
        abs_path = (project_dir / ".prompts" / filename).resolve()
        return (
            f"IMPORTANT: Your full instructions are in `{abs_path}`. "
            f"You MUST read that file with the Read tool BEFORE doing anything else. "
            f"Follow those instructions exactly."
        )
    return (
        f"IMPORTANT: Your full instructions are in `.prompts/{filename}`. "
        f"You MUST read that file with the Read tool BEFORE doing anything else. "
        f"Follow those instructions exactly."
    )


OrchestratorModelOption = Literal["haiku", "sonnet", "opus"]

# Valid orchestrator model values (no "inherit" option since orchestrator is root)
_VALID_ORCHESTRATOR_MODELS: Final[tuple[str, ...]] = ("haiku", "sonnet", "opus")


def _is_valid_orchestrator_model(value: str) -> TypeGuard[OrchestratorModelOption]:
    """Type guard to validate orchestrator model option values."""
    return value in _VALID_ORCHESTRATOR_MODELS


def get_orchestrator_model() -> OrchestratorModelOption:
    """
    Get the orchestrator model from environment variable or default.

    Environment variable: ORCHESTRATOR_MODEL
    Valid values: haiku, sonnet, opus (no "inherit" since orchestrator is root)
    Default: haiku
    """
    value = os.environ.get("ORCHESTRATOR_MODEL", "").lower().strip()
    if _is_valid_orchestrator_model(value):
        return value  # Type checker knows this is OrchestratorModelOption via TypeGuard
    return "haiku"


def create_agent_definitions(project_dir: Path | None = None) -> dict[str, AgentDefinition]:
    """
    Create agent definitions with models from environment configuration.

    Uses short stub prompts that tell agents to read their full instructions
    from .prompts/ files in the project directory. This keeps the CLI command
    line well under the Windows ~32768 char limit.

    Args:
        project_dir: Project directory for absolute prompt paths. When provided,
            stub prompts use absolute paths so sub-agents can find their prompt
            files regardless of working directory.
    """
    return {
        "linear": AgentDefinition(
            description="Manages Linear issues, project status, and session handoff. Use for any Linear operations.",
            prompt=_stub_prompt("linear", project_dir),
            tools=get_linear_tools() + FILE_TOOLS,
            model=_get_model("linear"),
        ),
        "github": AgentDefinition(
            description="Handles Git commits, branches, and GitHub PRs. Use for version control operations.",
            prompt=_stub_prompt("github", project_dir),
            tools=get_github_tools() + FILE_TOOLS + ["Bash"],
            model=_get_model("github"),
        ),
        "slack": AgentDefinition(
            description="Sends Slack notifications to keep users informed. Use for progress updates.",
            prompt=_stub_prompt("slack", project_dir),
            tools=get_slack_tools() + FILE_TOOLS,
            model=_get_model("slack"),
        ),
        "coding": AgentDefinition(
            description="Writes and tests code. Use when implementing features or fixing bugs.",
            prompt=_stub_prompt("coding", project_dir),
            tools=get_coding_tools(),
            model=_get_model("coding"),
        ),
    }
