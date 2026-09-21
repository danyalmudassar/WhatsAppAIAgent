import pytest

from app.graph import build_graph, local_message
from app.memory import MemoryStore
from app.tools import build_tool_registry


@pytest.fixture
def graph(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db", "secret")
    return build_graph(memory, build_tool_registry(memory))


@pytest.mark.parametrize(
    ("text", "route"),
    [("meri tasks dikhao", "personal_assistant"), ("sources ke sath research karo", "researcher"), ("Python error debug karo", "developer")],
)
def test_supervisor_routes_requests(graph, text, route):
    result = graph.invoke(local_message(text))
    assert result["route"] == route
