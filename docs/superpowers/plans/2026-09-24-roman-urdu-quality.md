# Natural Balanced Roman Urdu Response Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LangGraph and WhatsApp-facing responses consistently natural, concise, and readable Roman Urdu while preserving technical values and existing response contracts.

**Architecture:** Keep response shaping at the existing graph boundary. Replace the current heuristic that prepends `Roman Urdu jawab:` with an explicit, stable model instruction in `app/graph.py` and a conservative policy function in `app/policy.py` that only trims output and appends citations. Add behavior-focused tests using fake LLM output so tests do not depend on Ollama availability or one exact generated sentence.

**Tech Stack:** Python, LangGraph, pytest, existing `AgentState`/`OutgoingMessage` contracts, Ollama-compatible LLM adapter.

---

## File map

- Modify `app/graph.py`: central Roman Urdu instruction used by the LLM-backed LangGraph role node.
- Modify `app/policy.py`: remove unnatural prefix injection while retaining trimming, citation preservation, and confirmation policy.
- Modify `tests/test_policy.py`: verify clean output, ASCII/Roman Urdu constraints, citations, truncation, and exact-value preservation.
- Modify `tests/test_graph.py`: verify the LLM receives the approved style guidance and graph output preserves realistic Roman Urdu, technical terms, and fallback behavior.
- Modify `README.md`: document the natural balanced Roman Urdu contract for operators and contributors.

### Task 1: Lock the policy contract with failing tests

**Files:**
- Modify: `tests/test_policy.py`
- Reference: `app/policy.py`

- [ ] **Step 1: Add tests for clean natural output**

Extend `tests/test_policy.py` with:

```python
import pytest

from app.policy import apply_response_policy


def test_policy_does_not_add_an_artificial_prefix():
    assert apply_response_policy("The deployment is ready.") == "The deployment is ready."


def test_policy_preserves_natural_roman_urdu():
    text = "Aap ka deployment ready hai. Logs check karne ke liye command chalayein."
    assert apply_response_policy(text) == text


def test_policy_preserves_technical_values_and_citations():
    text = "Service restart ho gayi hai: railway service restart --service svc-123"
    result = apply_response_policy(text, ("https://example.com/status",))
    assert "railway service restart --service svc-123" in result
    assert "https://example.com/status" in result


def test_policy_truncates_at_word_boundary():
    result = apply_response_policy("Aap ka service status ready hai aur worker bhi chal raha hai.", max_chars=32)
    assert len(result) <= 35
    assert result.endswith("...")
    assert not result[:-3].endswith(" ")


@pytest.mark.parametrize("text", ["Yeh theek hai.", "Roman Urdu mein jawab dein."])
def test_policy_keeps_latin_script_output(text):
    result = apply_response_policy(text)
    assert not any("\u0600" <= character <= "\u06ff" for character in result)
```

- [ ] **Step 2: Run the focused tests and confirm the old behavior fails**

Run:

```bash
pytest tests/test_policy.py -q
```

Expected: the artificial-prefix test fails because the current implementation changes `"The deployment is ready."` to `"Roman Urdu jawab: The deployment is ready."`.

- [ ] **Step 3: Commit the failing test contract**

```bash
git add tests/test_policy.py
git commit -m "test: define natural Roman Urdu policy behavior"
```

### Task 2: Replace the brittle response-policy heuristic

**Files:**
- Modify: `app/policy.py:1-17`
- Test: `tests/test_policy.py`

- [ ] **Step 1: Implement conservative policy behavior**

Replace `apply_response_policy` with this behavior:

```python
def apply_response_policy(text: str, citations: tuple[str, ...] = (), max_chars: int = 3000) -> str:
    cleaned = text.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip() + "..."
    if citations:
        cleaned += "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations)
    return cleaned
```

Do not add automatic translation, word substitution, Urdu-script filtering, or
an English-to-Roman-Urdu prefix. The model instruction is the correct place to
shape language; this function must not rewrite user-visible meaning.

- [ ] **Step 2: Run policy tests**

Run:

```bash
pytest tests/test_policy.py -q
```

Expected: all policy tests pass.

- [ ] **Step 3: Commit the policy implementation**

```bash
git add app/policy.py tests/test_policy.py
git commit -m "fix: keep response policy natural and non-rewriting"
```

### Task 3: Add the approved model response instruction

**Files:**
- Modify: `app/graph.py:24-32`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Add a fake LLM test fixture and prompt assertions**

Add to `tests/test_graph.py`:

```python

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
```

- [ ] **Step 2: Run the new graph test and confirm it fails**

Run:

```bash
pytest tests/test_graph.py::test_llm_response_uses_natural_balanced_roman_urdu_policy -q
```

Expected: FAIL because the current prompt does not contain the complete
approved guidance.

- [ ] **Step 3: Replace the short graph prompt**

In `app/graph.py`, use one explicit prompt block:

```python
prompt = (
    "Aap ek personal AI agent hain. Natural aur balanced Roman Urdu mein "
    "short, clear jawab dein. Latin/ASCII script use karein; Urdu script na "
    "likhein. Urdu grammar ke sath zaroori English technical terms, product "
    "names, commands, code, URLs, filenames aur error codes ko bilkul "
    "preserve karein. Literal translation, filler, repeated conclusion aur "
    "unnecessary headings se bachein. User ke tone ke mutabiq respectful aur "
    "direct rahen. Contact data disclose na karein aur unexecuted action ka "
    "dawa na karein.\n"
    f"Role: {route}\nUser: {state['message'].text}"
)
```

Keep `apply_response_policy(answer)` as the single output boundary so the
WhatsApp polling path, `/messages`, and dashboard graph path retain the same
trimming and persistence behavior.

- [ ] **Step 4: Run all graph tests**

Run:

```bash
pytest tests/test_graph.py -q
```

Expected: all graph tests pass, including routing tests and the new prompt
contract.

- [ ] **Step 5: Commit graph prompt changes**

```bash
git add app/graph.py tests/test_graph.py
git commit -m "feat: guide llm toward natural balanced Roman Urdu"
```

### Task 4: Cover representative response scenarios and document the contract

**Files:**
- Modify: `tests/test_graph.py`
- Modify: `README.md`

- [ ] **Step 1: Add scenario tests using the fake LLM**

Add parameterized coverage for the approved examples:

```python
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
```

If the test suite’s existing fixtures make this parameterization awkward, use
individual test functions with the same assertions; do not assert one exact
model sentence.

- [ ] **Step 2: Document the response contract**

In `README.md`, add a short “Response language” section stating:

```markdown
## Response language

Agent responses use natural, balanced Roman Urdu in Latin script. Common
technical terms, product names, commands, URLs, filenames, identifiers, and
error codes remain in English when that keeps the answer clearer. Responses are
short and direct; the runtime does not perform automatic translation or
meaning-changing post-processing.
```

- [ ] **Step 3: Run the complete backend validation**

Run:

```bash
pytest -q
ruff check .
```

Expected: all tests pass and Ruff reports no violations.

- [ ] **Step 4: Review the final diff and commit**

Run:

```bash
git diff HEAD~3..HEAD -- app/policy.py app/graph.py tests/test_policy.py tests/test_graph.py README.md
git status --short
```

Confirm no generated `dashboard/.next/` or `dashboard/node_modules/` files are
included in the commit, then commit:

```bash
git add app/policy.py app/graph.py tests/test_policy.py tests/test_graph.py README.md
git commit -m "feat: improve Roman Urdu response quality"
```

## Self-review checklist

- Spec coverage: prompt guidance, no post-processing, four representative
  generated-response scenarios plus policy-level URL/command coverage,
  preserved technical values, and backend validation are covered in Tasks 1–4.
- Completeness scan: no unfinished or unspecified implementation steps remain.
- Type consistency: `RecordingLLM.invoke()` returns an object with `.content`,
  matching the existing `getattr(generated, "content", str(generated))` path;
  all graph tests continue to use `build_graph()` and `local_message()`.
- Scope: no dashboard authentication/status labels, provider contracts,
  persistence, memory format, or WhatsApp transport code is changed.
