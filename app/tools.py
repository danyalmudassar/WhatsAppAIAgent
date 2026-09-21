from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel

from app.contracts import ToolResult
from app.memory import MemoryStore
from app.security import require_confirmation


class ProfileArgs(BaseModel):
    field: str
    confirmed: bool = False


class TaskArgs(BaseModel):
    title: str
    due_at: str | None = None


class ReadArgs(BaseModel):
    path: str


class WriteArgs(BaseModel):
    operation: str
    payload: str
    confirmed: bool = False


def build_tool_registry(memory: MemoryStore, workspace_root: Path = Path(".")) -> dict[str, object]:
    @tool(args_schema=ProfileArgs)
    def profile_lookup(field: str, confirmed: bool = False) -> ToolResult:
        """Read one approved profile field."""
        if field.lower() in {"email", "phone", "whatsapp"} and not require_confirmation("profile_contact", confirmed):
            return ToolResult(ok=True, content="[protected]")
        profile = memory.get_profile(include_contacts=confirmed)
        return ToolResult(ok=True, content=str(profile.get(field, "[not found]")))

    @tool(args_schema=TaskArgs)
    def task_create(title: str, due_at: str | None = None) -> ToolResult:
        """Create a local task."""
        return ToolResult(ok=True, content=memory.create_task(title, due_at))

    @tool
    def task_list() -> ToolResult:
        """List open local tasks."""
        return ToolResult(ok=True, content=str(memory.list_tasks()))

    @tool(args_schema=ReadArgs)
    def workspace_read(path: str) -> ToolResult:
        """Read a permitted workspace file."""
        root = workspace_root.resolve()
        candidate = (root / path).resolve()
        if root not in candidate.parents and candidate != root:
            return ToolResult(ok=False, content="path rejected", error_code="path_traversal")
        try:
            return ToolResult(ok=True, content=candidate.read_text()[:12000])
        except OSError as exc:
            return ToolResult(ok=False, content=str(exc), error_code="workspace_read_failed")

    @tool(args_schema=WriteArgs)
    def github_write(operation: str, payload: str, confirmed: bool = False) -> ToolResult:
        """Request a GitHub write, requiring explicit confirmation."""
        if not require_confirmation("github_write", confirmed):
            return ToolResult(ok=False, content="explicit confirmation required", error_code="confirmation_required")
        return ToolResult(ok=False, content="GitHub write provider is not configured", error_code="provider_unavailable")

    @tool
    def calculate(expression: str) -> ToolResult:
        """Evaluate a basic arithmetic expression."""
        if not all(char in "0123456789+-*/(). " for char in expression):
            return ToolResult(ok=False, content="unsafe expression", error_code="invalid_expression")
        try:
            return ToolResult(ok=True, content=str(eval(expression, {"__builtins__": {}}, {})))
        except (ArithmeticError, SyntaxError, TypeError, ValueError) as exc:
            return ToolResult(ok=False, content=str(exc), error_code="calculation_failed")

    return {
        "profile_lookup": profile_lookup,
        "task_create": task_create,
        "task_list": task_list,
        "workspace_read": workspace_read,
        "github_write": github_write,
        "calculate": calculate,
    }
