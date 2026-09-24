from typing import Any

from app.decision_models import DecisionRequest, DecisionResponse


class DecisionMcpServer:
    def __init__(self, router):
        self.router = router

    async def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = DecisionRequest.model_validate(payload)
        result: DecisionResponse = await self.router.decide(request)
        return result.model_dump(mode="json")

    async def route(self, state: dict[str, Any] | str) -> dict[str, Any]:
        return await self.decide(
            {
                "state": state,
                "questions": {
                    "route": {
                        "type": "choice",
                        "instructions": "Choose the coding or agent workflow.",
                        "criteria": {
                            "personal_assistant": "tasks and reminders",
                            "researcher": "research and sources",
                            "developer": "code and debugging",
                        },
                    }
                },
            }
        )

    async def risk_check(self, state: dict[str, Any] | str) -> dict[str, Any]:
        return await self.decide(
            {
                "state": state,
                "questions": {
                    "risk": {
                        "type": "noul",
                        "instructions": "Does this request involve high-risk action?",
                    }
                },
            }
        )

    def review_required(self, decision: dict[str, Any]) -> dict[str, bool]:
        confidence = decision.get("confidence")
        required = bool(decision.get("review_required")) or decision.get("reason_code") in {
            "low_confidence",
            "all_backends_failed",
            "backend_unavailable",
            "backend_timeout",
            "backend_auth_failed",
        }
        if confidence is None:
            required = True
        return {"review_required": required}


def create_mcp_server(router):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the decision-mcp extra to run the MCP server") from exc

    adapter = DecisionMcpServer(router)
    server = FastMCP("system-one-decision-router")

    @server.tool()
    async def decide(payload: dict[str, Any]) -> dict[str, Any]:
        return await adapter.decide(payload)

    @server.tool()
    async def route(state: dict[str, Any] | str) -> dict[str, Any]:
        return await adapter.route(state)

    @server.tool()
    async def risk_check(state: dict[str, Any] | str) -> dict[str, Any]:
        return await adapter.risk_check(state)

    @server.tool()
    def review_required(decision: dict[str, Any]) -> dict[str, bool]:
        return adapter.review_required(decision)

    return server
