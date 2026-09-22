import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException
from ollama import ResponseError

from app.config import Settings
from app.contracts import IncomingMessage, OutgoingMessage
from app.graph import build_graph
from app.llm import create_ollama_chat_model
from app.memory import MemoryStore
from app.tools import build_tool_registry
from app.whatsapp import MockWhatsAppAdapter, OfficialWhatsAppAdapter

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, graph=None, memory=None) -> FastAPI:
    settings = settings or Settings()
    memory = memory or MemoryStore(settings.memory_path, settings.memory_key.get_secret_value())
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
                processed.append(await adapter.send(response))
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
                worker_error = f"HTTP {exc.response.status_code}"
                logger.error("WhatsApp polling failed with HTTP %s", exc.response.status_code)
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
