"""Native Hermes plugin: shared GitHub operations and bundled workflow skill."""
import json
import shutil
from pathlib import Path

from .github_projects import GitHubError, execute


def _handler(operation):
    def handle(arguments, **kwargs):
        try:
            return json.dumps({"ok": True, "data": execute(operation, arguments)})
        except GitHubError as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        except Exception:
            return json.dumps({"ok": False, "error": "Unexpected plugin failure. Refresh GitHub before retrying any write."})
    return handle


def register(ctx):
    string = {"type": "string"}
    positive = {"type": "integer", "minimum": 1}
    strings = {"type": "array", "items": string}
    repo = {"repo": {"type": "string", "description": "Exact owner/repository."}}
    issue = {**repo, "number": positive}
    project = {"owner": string, "number": positive}
    operations = [
        ("list", "projects", "List projects for the authenticated GitHub account and its organizations. Optionally restrict to an exact owner.", {"owner": string}, []),
        ("board", "board", "Read all project cards and Status options. Includes issues, PRs, and drafts.", project, ["owner", "number"]),
        ("issue", "issue", "Read an issue and its comments before editing; retain updatedAt for concurrency checks.", issue, ["repo", "number"]),
        ("create_issue", "create_issue", "Create an issue and add it to the selected project. Only on explicit request. Do not blindly retry failures.", {**repo, "title": string, "body": string, "labels": strings, "assignees": strings, "owner": string, "project_number": positive}, ["repo", "title", "body", "owner", "project_number"]),
        ("update_issue", "update_issue", "Update an issue on explicit request. Labels and assignees replace the entire list. Requires the previously read updatedAt.", {**issue, "title": string, "body": string, "labels": strings, "assignees": strings, "expected_updated_at": string}, ["repo", "number", "expected_updated_at"]),
        ("comment", "comment", "Post an explicitly requested issue comment. Do not blindly retry after an uncertain result.", {**issue, "body": string}, ["repo", "number", "body"]),
        ("issue_state", "issue_state", "Explicitly close or reopen an issue, separate from moving its project card.", {**issue, "state": {"type": "string", "enum": ["OPEN", "CLOSED"]}, "expected_updated_at": string}, ["repo", "number", "state", "expected_updated_at"]),
        ("move", "move", "Move a project card to a Status option. Read board first; pass its current status and the exact option ID.", {**project, "item_id": string, "option_id": string, "expected_status": {"type": ["string", "null"]}}, ["owner", "number", "item_id", "option_id", "expected_status"]),
    ]
    for suffix, operation, description, properties, required in operations:
        name = f"github_projects_{suffix}"
        ctx.register_tool(name=name, toolset="github-projects", schema={
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        }, handler=_handler(operation), check_fn=lambda: shutil.which("gh") is not None)
    ctx.register_skill("github-projects", Path(__file__).parent / "skills" / "github-projects" / "SKILL.md")
