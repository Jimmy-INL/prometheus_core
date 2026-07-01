"""Workflow library package for compiled templates, matching, and execution."""

from .registry import WorkflowRegistry, get_workflow_registry
from .matcher import WorkflowMatch, match_workflows
from .executor import execute_workflow
from .health import verify_workflow_source_health
from .naming import find_workflow_by_command, workflow_command_aliases, workflow_slug, workflow_tool_name

__all__ = [
    "WorkflowRegistry",
    "get_workflow_registry",
    "WorkflowMatch",
    "match_workflows",
    "execute_workflow",
    "verify_workflow_source_health",
    "find_workflow_by_command",
    "workflow_command_aliases",
    "workflow_slug",
    "workflow_tool_name",
]
