import pytest

from app.graph import build_graph, local_message
from app.memory import MemoryStore
from app.tools import build_tool_registry


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class RecordingLLM:
    def __init__(self, content: str):
        self.content = content
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return FakeResponse(self.content)


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


def test_llm_response_uses_natural_balanced_roman_urdu_policy(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db", "secret")
    llm = RecordingLLM("Aap ka deployment ready hai. Command `railway status` chalayein.")
    graph = build_graph(memory, build_tool_registry(memory), llm=llm)

    result = graph.invoke(local_message("deployment status batao"))

    prompt = llm.prompts[0]
    assert "Roman Urdu" in prompt
    assert "Latin" in prompt
    assert "technical terms" in prompt
    assert "short" in prompt
    assert result["response"].text == llm.content


@pytest.mark.parametrize(
    ("generated", "required"),
    [
        ("Assalam o alaikum! Aaj aap kaise hain?", "Assalam"),
        ("Aap ka API request fail hui hai. Error code 401 ko check karein.", "401"),
        ("Service unavailable hai. `curl https://example.com/healthz` chalayein.", "https://example.com/healthz"),
        ("Theek hai, main isay WhatsApp par short reply mein samjha deta hoon.", "WhatsApp"),
    ],
)
def test_representative_responses_keep_meaningful_terms(tmp_path, generated, required):
    memory = MemoryStore(tmp_path / f"{required.replace('/', '_')}.db", "secret")
    graph = build_graph(memory, build_tool_registry(memory), llm=RecordingLLM(generated))

    result = graph.invoke(local_message("madad chahiye"))

    assert required in result["response"].text
    assert not any("\u0600" <= character <= "\u06ff" for character in result["response"].text)
