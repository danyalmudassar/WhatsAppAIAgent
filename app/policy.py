def apply_response_policy(text: str, citations: tuple[str, ...] = (), max_chars: int = 3000) -> str:
    cleaned = text.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip() + "..."
    if citations:
        cleaned += "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations)
    return cleaned


def requires_confirmation_for(action: str) -> bool:
    return action in {"profile_contact", "github_write", "outbound_message", "destructive_operation"}
