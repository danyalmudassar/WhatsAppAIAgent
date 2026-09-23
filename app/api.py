import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import Cookie, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ollama import ResponseError

from app.auth import active_session, create_session, verify_password
from app.config import Settings
from app.contracts import IncomingMessage, OutgoingMessage
from app.dashboard_models import AgentConfig, AuditEvent, ProviderConfig
from app.dashboard_services import AgentService, ChatService, ProviderService
from app.dashboard_store import DashboardStore
from app.events import EventRecorder
from app.graph import build_graph
from app.llm import create_ollama_chat_model
from app.memory import MemoryStore
from app.providers import ProviderError
from app.tools import build_tool_registry
from app.whatsapp import MockWhatsAppAdapter, OfficialWhatsAppAdapter

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, graph=None, memory=None) -> FastAPI:
    settings = settings or Settings()
    memory = memory or MemoryStore(settings.memory_path, settings.memory_key.get_secret_value())
    dashboard_store = DashboardStore(settings.memory_path, settings.memory_key.get_secret_value())
    events = EventRecorder(dashboard_store)
    if graph is None:
        llm = None
        if settings.ollama_api_key and settings.ollama_api_key.get_secret_value().strip():
            llm = create_ollama_chat_model(settings)
        graph = build_graph(memory, build_tool_registry(memory, settings.workspace_root), llm=llm)
    adapter = (
        OfficialWhatsAppAdapter(settings, memory)
        if settings.whatsapp_enabled
        else MockWhatsAppAdapter()
    )
    poll_lock = asyncio.Lock()
    worker_error: str | None = None

    def require_admin(authorization: str | None) -> None:
        expected = settings.app_admin_token.get_secret_value()
        if authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="admin authorization required")
    async def process_messages(messages):
        processed = []
        for message in messages:
            if not memory.mark_event_if_new(message.message_id):
                continue
            try:
                events.record("message_received", message.message_id, {"source": "whatsapp"})
                events.record("agent_selected", message.message_id, {"source": "whatsapp"})
                result = await asyncio.to_thread(
                    graph.invoke,
                    {
                        "message": message,
                        "history": [],
                        "memory_context": {},
                        "route": "",
                        "tool_results": [],
                        "response": None,
                    },
                )
            except ResponseError as exc:
                raise RuntimeError("Ollama Cloud rejected OLLAMA_API_KEY") from exc
            response = result["response"].model_copy(update={"recipient_id": message.sender_id})
            try:
                events.record("response_ready", message.message_id, {"source": "whatsapp"})
                processed.append(await adapter.send(response))
                events.record("message_delivered", message.message_id, {"source": "whatsapp"})
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200].replace("\n", " ")
                raise RuntimeError(
                    f"WhatsApp message delivery failed with HTTP "
                    f"{exc.response.status_code}: {detail}"
                ) from exc
        return processed

    async def whatsapp_worker():
        nonlocal worker_error
        retry_seconds = settings.whatsapp_retry_base_seconds
        while True:
            try:
                async with poll_lock:
                    messages = await adapter.receive(limit=50, timeout=25)
                await process_messages(messages)
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200].replace("\n", " ")
                worker_error = f"HTTP {exc.response.status_code}: {detail}"
                logger.error(
                    "WhatsApp upstream request failed with HTTP %s: %s",
                    exc.response.status_code,
                    detail,
                )
                await asyncio.sleep(retry_seconds)
                retry_seconds = min(retry_seconds * 2, settings.whatsapp_retry_max_seconds)
            except (httpx.TimeoutException, httpx.RequestError, RuntimeError, ValueError) as exc:
                worker_error = str(exc)
                logger.error("WhatsApp worker error: %s", exc)
                await asyncio.sleep(retry_seconds)
                retry_seconds = min(retry_seconds * 2, settings.whatsapp_retry_max_seconds)
            else:
                worker_error = None
                retry_seconds = settings.whatsapp_retry_base_seconds
                await asyncio.sleep(settings.whatsapp_poll_interval)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        worker = asyncio.create_task(whatsapp_worker()) if settings.whatsapp_enabled else None
        try:
            yield
        finally:
            if worker is not None:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    app = FastAPI(title="Personal WhatsApp AI Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dashboard_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    def require_session(session: str | None):
        record = active_session(dashboard_store, session)
        if not record:
            raise HTTPException(status_code=401, detail="login required")
        return record

    agent_service = AgentService(dashboard_store)
    provider_service = ProviderService(dashboard_store)
    chat_service = ChatService(dashboard_store, provider_service)

    @app.post("/auth/login")
    async def login(request: Request):
        body = await request.json()
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        if username != settings.owner_username or not verify_password(password, settings.owner_password_hash.get_secret_value()):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = create_session(dashboard_store, username, settings.session_ttl_seconds)
        response = {"status": "authenticated", "username": username}
        from fastapi.responses import JSONResponse
        result = JSONResponse(response)
        result.set_cookie(
            "dashboard_session",
            token,
            httponly=True,
            secure=settings.dashboard_origin.startswith("https://"),
            samesite="lax",
            max_age=settings.session_ttl_seconds,
        )
        return result

    @app.post("/auth/logout")
    def logout(dashboard_session: str | None = Cookie(default=None)):
        if dashboard_session:
            dashboard_store.revoke_session(dashboard_session)
        from fastapi.responses import JSONResponse
        result = JSONResponse({"status": "logged_out"})
        result.delete_cookie("dashboard_session")
        return result

    @app.get("/auth/session")
    def session_info(dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        return {"username": record.actor, "role": record.role, "expires_at": record.expires_at}

    @app.get("/dashboard/overview")
    def dashboard_overview(dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        return {
            "status": "degraded" if worker_error else "ready",
            "whatsapp_enabled": settings.whatsapp_enabled,
            "worker_error": worker_error,
            "agents": len(dashboard_store.list_agents()),
            "providers": len(dashboard_store.list_providers()),
        }

    @app.get("/dashboard/events")
    def dashboard_events(cursor: int = 0, dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        return {"events": [event.model_dump(mode="json") for _, event in dashboard_store.events_after(cursor)]}

    @app.get("/dashboard/events/stream")
    async def dashboard_event_stream(request: Request, dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        cursor = int(request.headers.get("last-event-id", "0") or 0)
        return StreamingResponse(events.subscribe(cursor), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/dashboard/agents")
    def dashboard_agents(dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        return {"agents": [agent.model_dump() for agent in dashboard_store.list_agents()]}

    @app.delete("/dashboard/agents/{agent_id}")
    def delete_agent(agent_id: str, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        try:
            dashboard_store.delete_agent(agent_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        dashboard_store.append_audit(AuditEvent(
            id=f"audit-{secrets.token_urlsafe(8)}", timestamp=datetime.now(UTC),
            actor=record.actor, action="delete", resource=f"agent:{agent_id}", result="ok",
        ))
        events.record("config_changed", agent_id, {"action": "agent_deleted"})
        return {"status": "deleted"}

    @app.post("/dashboard/agents")
    async def create_agent(request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        agent = AgentConfig.model_validate(await request.json())
        saved = dashboard_store.save_agent(agent)
        events.record("config_changed", agent.id, {"action": "agent_saved", "actor": record.actor})
        return saved

    @app.put("/dashboard/agents/{agent_id}")
    async def update_agent(agent_id: str, request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        if body.get("id", agent_id) != agent_id:
            raise HTTPException(status_code=422, detail="agent id mismatch")
        try:
            saved = agent_service.save(
                AgentConfig.model_validate({**body, "id": agent_id}),
                expected_revision=body.get("revision"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        dashboard_store.append_audit(AuditEvent(
            id=f"audit-{secrets.token_urlsafe(8)}", timestamp=datetime.now(UTC),
            actor=record.actor, action="update", resource=f"agent:{agent_id}",
            revision=saved.revision, result="ok",
        ))
        events.record("config_changed", agent_id, {"action": "agent_updated", "actor": record.actor})
        return saved

    @app.get("/dashboard/providers")
    def dashboard_providers(dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        return {"providers": [provider.model_dump() for provider in dashboard_store.list_providers()]}

    @app.post("/dashboard/chat")
    async def dashboard_chat(request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(status_code=422, detail="text is required")
        if dashboard_store.list_agents() and dashboard_store.list_providers():
            try:
                result = await chat_service.generate(
                    record.actor, text, body.get("conversation_id"), body.get("agent_id")
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            events.record("response_ready", result.conversation_id, {"provider_id": result.provider_id})
            return {
                "conversation_id": result.conversation_id,
                "text": result.text,
                "provider_id": result.provider_id,
            }
        message = IncomingMessage(message_id=f"dashboard-{id(body)}", sender_id=record.actor, text=text)
        events.record("message_received", message.message_id, {"source": "dashboard"})
        result = await asyncio.to_thread(graph.invoke, {
            "message": message, "history": [], "memory_context": {},
            "route": "", "tool_results": [], "response": None,
        })
        events.record("response_ready", message.message_id, {"source": "dashboard"})
        return result["response"]

    @app.get("/dashboard/chat/stream")
    async def dashboard_chat_stream(
        text: str,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        dashboard_session: str | None = Cookie(default=None),
    ):
        record = require_session(dashboard_session)
        if not text.strip():
            raise HTTPException(status_code=422, detail="text is required")

        async def generate():
            try:
                result = await chat_service.generate(record.actor, text.strip(), conversation_id, agent_id)
                yield f"event: complete\ndata: {json.dumps({'conversation_id': result.conversation_id, 'text': result.text, 'provider_id': result.provider_id})}\n\n"
            except (KeyError, RuntimeError, ProviderError, httpx.HTTPError) as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/dashboard/providers")
    async def create_provider(request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        provider = ProviderConfig.model_validate(body)
        saved = dashboard_store.save_provider(provider, body.get("secret"))
        events.record("config_changed", provider.id, {"action": "provider_saved", "actor": record.actor, "api_key": body.get("secret", "")})
        return saved

    @app.put("/dashboard/providers/{provider_id}")
    async def update_provider(provider_id: str, request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        if body.get("id", provider_id) != provider_id:
            raise HTTPException(status_code=422, detail="provider id mismatch")
        try:
            saved = provider_service.save(
                ProviderConfig.model_validate({**body, "id": provider_id}),
                body.get("secret"),
                expected_revision=body.get("revision"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        dashboard_store.append_audit(AuditEvent(
            id=f"audit-{secrets.token_urlsafe(8)}", timestamp=datetime.now(UTC),
            actor=record.actor, action="update", resource=f"provider:{provider_id}",
            revision=saved.revision, result="ok",
        ))
        events.record("config_changed", provider_id, {"action": "provider_updated", "actor": record.actor})
        return saved

    @app.post("/dashboard/providers/{provider_id}/test")
    async def test_provider(provider_id: str, dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        provider = next((item for item in dashboard_store.list_providers() if item.id == provider_id), None)
        if provider is None:
            raise HTTPException(status_code=404, detail="provider not found")
        started = asyncio.get_running_loop().time()
        try:
            await provider_service.provider(provider).generate(
                [{"role": "user", "content": "health check"}]
            )
        except (ProviderError, RuntimeError, httpx.HTTPError) as exc:
            return {
                "status": "failed",
                "provider_id": provider_id,
                "latency_ms": round((asyncio.get_running_loop().time() - started) * 1000),
                "error": str(exc),
            }
        return {
            "status": "ok",
            "provider_id": provider_id,
            "latency_ms": round((asyncio.get_running_loop().time() - started) * 1000),
        }

    @app.delete("/dashboard/providers/{provider_id}")
    def delete_provider(provider_id: str, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        try:
            dashboard_store.delete_provider(provider_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        dashboard_store.append_audit(AuditEvent(
            id=f"audit-{secrets.token_urlsafe(8)}", timestamp=datetime.now(UTC),
            actor=record.actor, action="delete", resource=f"provider:{provider_id}", result="ok",
        ))
        events.record("config_changed", provider_id, {"action": "provider_deleted"})
        return {"status": "deleted"}

    @app.get("/dashboard/audit")
    def dashboard_audit(cursor: int = 0, limit: int = 100, dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        records = dashboard_store.audit_after(cursor, min(limit, 100))
        return {
            "audit": [event.model_dump(mode="json") for _, event in records],
            "next_cursor": records[-1][0] if records else cursor,
        }

    @app.get("/dashboard/conversations")
    def dashboard_conversations(dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        return {"conversations": [item.model_dump(mode="json") for item in dashboard_store.list_conversations(record.actor)]}

    @app.post("/dashboard/conversations")
    async def create_conversation(request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        conversation_id = body.get("id") or f"conversation-{secrets.token_urlsafe(8)}"
        conversation = dashboard_store.create_conversation(conversation_id, record.actor, body.get("agent_id"))
        return conversation

    @app.get("/dashboard/conversations/{conversation_id}/messages")
    def conversation_messages(
        conversation_id: str,
        cursor: int = 0,
        limit: int = 100,
        dashboard_session: str | None = Cookie(default=None),
    ):
        record = require_session(dashboard_session)
        conversation = dashboard_store.get_conversation(conversation_id)
        if conversation is None or conversation.actor != record.actor:
            raise HTTPException(status_code=404, detail="conversation not found")
        messages, next_cursor = dashboard_store.list_messages(conversation_id, cursor, min(limit, 100))
        return {"messages": [item.model_dump(mode="json") for item in messages], "next_cursor": next_cursor}

    @app.get("/dashboard/settings")
    def dashboard_settings(dashboard_session: str | None = Cookie(default=None)):
        require_session(dashboard_session)
        return {"settings": dashboard_store.list_settings()}

    @app.put("/dashboard/settings")
    async def update_dashboard_settings(request: Request, dashboard_session: str | None = Cookie(default=None)):
        record = require_session(dashboard_session)
        body = await request.json()
        for key, value in body.items():
            if key in {"default_agent_id"}:
                dashboard_store.set_setting(key, str(value))
        events.record("config_changed", record.actor, {"action": "settings_updated", "actor": record.actor})
        return {"status": "updated"}

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        if settings.whatsapp_enabled and worker_error:
            raise HTTPException(status_code=503, detail="WhatsApp worker is degraded")
        try:
            with memory._connect() as db:
                db.execute("SELECT 1").fetchone()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="memory store unavailable") from exc
        return {"status": "ready", "whatsapp_worker": "ok" if settings.whatsapp_enabled else "disabled"}

    @app.post("/messages", response_model=OutgoingMessage)
    def messages(message: IncomingMessage):
        result = graph.invoke(
            {
                "message": message,
                "history": [],
                "memory_context": {},
                "route": "",
                "tool_results": [],
                "response": None,
            }
        )
        return result["response"]

    @app.post("/webhooks/whatsapp")
    async def whatsapp(payload: dict[str, object]):
        if settings.whatsapp_enabled:
            raise HTTPException(status_code=405, detail="official agents use GET /agent/poll")
        try:
            message = adapter.parse(payload)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid webhook payload") from exc
        if not memory.mark_event_if_new(message.message_id):
            return {"status": "duplicate", "message_id": message.message_id}
        result = graph.invoke(
            {
                "message": message,
                "history": [],
                "memory_context": {},
                "route": "",
                "tool_results": [],
                "response": None,
            }
        )
        response = result["response"].model_copy(update={"recipient_id": message.sender_id})
        delivery = await adapter.send(response)
        return {"status": "processed", "response": delivery}

    @app.post("/agent/poll")
    async def poll_agent(
        limit: int = 50,
        timeout: int = 15,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        if not settings.whatsapp_enabled:
            raise HTTPException(status_code=409, detail="WhatsApp agent is disabled")
        try:
            async with poll_lock:
                messages = await adapter.receive(limit=limit, timeout=timeout)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise HTTPException(
                    status_code=502,
                    detail="WhatsApp API rejected the API key (401 Unauthorized)",
                ) from exc
            raise HTTPException(
                status_code=502,
                detail=f"WhatsApp API returned HTTP {exc.response.status_code}",
            ) from exc
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise HTTPException(
                status_code=502,
                detail="WhatsApp API network request failed",
            ) from exc
        try:
            processed = await process_messages(messages)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"status": "processed", "count": len(processed), "messages": processed}

    @app.get("/memory/export")
    def export_memory(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return memory.export_json()

    @app.post("/memory/forget/{category}")
    def forget_memory(category: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if category not in {"profile", "preferences", "summaries", "tasks"}:
            raise HTTPException(status_code=400, detail="invalid memory category")
        memory.forget(category)
        return {"status": "forgotten", "category": category}

    return app
