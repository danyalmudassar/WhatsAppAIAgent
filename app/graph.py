from langgraph.graph import END, StateGraph

from app.contracts import AgentState, IncomingMessage, OutgoingMessage
from app.memory import MemoryStore
from app.policy import apply_response_policy


def _route(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("research", "source", "sources", "search", "تحقیق")):
        return "researcher"
    if any(word in lowered for word in ("python", "code", "debug", "github", "program")):
        return "developer"
    return "personal_assistant"


def build_graph(memory: MemoryStore, tools: dict[str, object], llm=None):
    def load_memory(state: AgentState):
        return {"memory_context": {"profile": memory.get_profile()}}

    def supervisor(state: AgentState):
        return {"route": _route(state["message"].text)}

    def role_node(state: AgentState):
        text = state["message"].text.lower()
        route = state["route"]
        if llm is not None:
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
            try:
                generated = llm.invoke(prompt)
                answer = getattr(generated, "content", str(generated))
            except (ConnectionError, OSError, RuntimeError, TimeoutError) as exc:
                answer = f"Ollama Cloud abhi unavailable hai: {type(exc).__name__}"
        elif route == "personal_assistant" and "task" in text:
            result = tools["task_list"].invoke({})
            answer = f"Aap ke tasks: {result.content}"
        elif route == "personal_assistant" and "profile" in text:
            answer = f"Aap ki protected profile summary: {state['memory_context']['profile']}"
        elif route == "researcher":
            answer = "Research provider abhi configure nahi hai; main fabricated source nahi dunga."
        else:
            answer = "Developer mode ready hai. Workspace file ka path dein, main safe read-only analysis karunga."
        return {"response": OutgoingMessage(message_id=state["message"].message_id, text=apply_response_policy(answer))}

    def persist_summary(state: AgentState):
        memory.save_summary(state["message"].message_id, state["response"].text)
        return {}

    graph = StateGraph(AgentState)
    for name, node in (("load_memory", load_memory), ("supervisor", supervisor), ("role", role_node), ("persist", persist_summary)):
        graph.add_node(name, node)
    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "supervisor")
    graph.add_edge("supervisor", "role")
    graph.add_edge("role", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def local_message(text: str, message_id: str = "local-1") -> dict:
    return {
        "message": IncomingMessage(message_id=message_id, sender_id="self", text=text),
        "history": [],
        "memory_context": {},
        "route": "",
        "tool_results": [],
        "response": None,
    }
