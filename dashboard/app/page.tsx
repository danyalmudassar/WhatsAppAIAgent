"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_ORIGIN ?? "https://whatsappaiagent-production-63d3.up.railway.app";

type Agent = { id: string; name: string; system_prompt: string; response_language: string; memory_profile: string; tools: string[]; provider_ids: string[]; enabled: boolean; revision: number };
type Provider = { id: string; type: string; name: string; base_url: string; model: string; enabled: boolean; priority: number; has_secret: boolean; secret_last_four?: string; revision: number };
type Conversation = { id: string; title: string; agent_id?: string; updated_at: string };
type Message = { id: string; role: string; content: string; provider_id?: string };
type Item = Record<string, unknown>;

class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, String(body.detail ?? `Request failed (${response.status})`));
  return body as T;
}

const blankAgent: Agent = { id: "", name: "", system_prompt: "", response_language: "roman_urdu", memory_profile: "default", tools: [], provider_ids: [], enabled: true, revision: 0 };
const blankProvider: Provider = { id: "", type: "ollama", name: "", base_url: "https://ollama.com", model: "", enabled: true, priority: 0, has_secret: false, revision: 0 };

export default function Dashboard() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState<Item | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [events, setEvents] = useState<Item[]>([]);
  const [audit, setAudit] = useState<Item[]>([]);
  const [agent, setAgent] = useState<Agent>(blankAgent);
  const [provider, setProvider] = useState<Provider>(blankProvider);
  const [secret, setSecret] = useState("");
  const [testResult, setTestResult] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState("");
  const [streaming, setStreaming] = useState(false);

  async function load() {
    const [summary, agentData, providerData, auditData, eventData] = await Promise.all([
      request<Item>("/dashboard/overview"), request<{ agents: Agent[] }>("/dashboard/agents"),
      request<{ providers: Provider[] }>("/dashboard/providers"), request<{ audit: Item[] }>("/dashboard/audit"),
      request<{ events: Item[] }>("/dashboard/events"),
    ]);
    setOverview(summary); setAgents(agentData.agents); setProviders(providerData.providers); setAudit(auditData.audit); setEvents(eventData.events);
    const chat = await request<{ conversations: Conversation[] }>("/dashboard/conversations");
    setConversations(chat.conversations);
    return summary;
  }

  useEffect(() => {
    load().then(() => setAuthenticated(true))
      .catch((cause: Error) => {
        setAuthenticated(false);
        if (cause instanceof ApiError && cause.status !== 401) setError(cause.message);
      });
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const source = new EventSource(`${API}/dashboard/events/stream`, { withCredentials: true });
    source.onmessage = (event) => setEvents((current) => [JSON.parse(event.data) as Item, ...current].slice(0, 100));
    source.onerror = () => {
      setError("Live activity stream disconnected; please sign in again.");
      setAuthenticated(false);
      source.close();
    };
    return () => source.close();
  }, [authenticated]);

  async function login(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); await load(); setAuthenticated(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Login failed"); }
  }

  async function saveAgent(event: FormEvent) {
    event.preventDefault(); setError("");
    const payload = { ...agent, tools: agent.tools.filter(Boolean), provider_ids: agent.provider_ids.filter(Boolean) };
    try {
      const saved = await request<Agent>(agent.revision ? `/dashboard/agents/${agent.id}` : "/dashboard/agents", { method: agent.revision ? "PUT" : "POST", body: JSON.stringify(payload) });
      setAgents((items) => [...items.filter((item) => item.id !== saved.id), saved]); setAgent(saved);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Agent save failed"); }
  }

  async function saveProvider(event: FormEvent) {
    event.preventDefault(); setError(""); const payload = { ...provider, secret: secret || undefined };
    try {
      const saved = await request<Provider>(provider.revision ? `/dashboard/providers/${provider.id}` : "/dashboard/providers", { method: provider.revision ? "PUT" : "POST", body: JSON.stringify(payload) });
      setProviders((items) => [...items.filter((item) => item.id !== saved.id), saved]); setProvider(saved); setSecret("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Provider save failed"); }
  }

  async function remove(path: string, label: string) {
    if (!window.confirm(`Delete ${label}?`)) return;
    try { await request(path, { method: "DELETE" }); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Delete failed"); }
  }

  async function testProvider() {
    if (!provider.id) return;
    try { const result = await request<{ status: string; error?: string }>(`/dashboard/providers/${provider.id}/test`, { method: "POST" }); setTestResult(result.error ? `${result.status}: ${result.error}` : result.status); }
    catch (cause) { setTestResult(cause instanceof Error ? cause.message : "Connection test failed"); }
  }

  async function selectConversation(id: string) {
    setConversationId(id);
    const result = await request<{ messages: Message[] }>(`/dashboard/conversations/${id}/messages`);
    setMessages(result.messages);
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault(); if (!message.trim() || streaming) return;
    setStreaming(true); setError("");
    const text = message.trim(); setMessage("");
    const params = new URLSearchParams({ text }); if (conversationId) params.set("conversation_id", conversationId);
    const source = new EventSource(`${API}/dashboard/chat/stream?${params.toString()}`, { withCredentials: true });
    source.addEventListener("complete", (event) => {
      const result = JSON.parse((event as MessageEvent).data) as { conversation_id: string; text: string };
      setConversationId(result.conversation_id); setMessages((items) => [...items, { id: `local-${Date.now()}`, role: "assistant", content: result.text }]);
      setStreaming(false); source.close(); void load();
    });
    source.addEventListener("error", () => { setError("Chat failed; check provider configuration."); setStreaming(false); source.close(); });
  }

  async function logout() { await request("/auth/logout", { method: "POST" }); setAuthenticated(false); }

  if (authenticated === null) return <main><p className="muted">Connecting to control center...</p></main>;
  if (!authenticated) return <main><form className="login card" onSubmit={login}><h1>Agent Control Center</h1><p className="muted">Sign in to manage your agent.</p>{error && <p className="bad">{error}</p>}<label>Username<input className="input" value={username} onChange={(e) => setUsername(e.target.value)} /></label><label>Password<input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label><button className="button">Sign in</button></form></main>;

  return <main><div className="shell"><nav className="nav"><h1>Agent Control Center</h1>{["overview", "chat", "agents", "providers", "activity", "audit"].map((name) => <button className="navlink" key={name} onClick={() => setTab(name)}>{name}</button>)}<button className="navlink" onClick={logout}>Sign out</button></nav><section><h2>Personal AI Workspace</h2>{error && <p className="bad">{error}</p>}
    {tab === "overview" && <><p className="muted">Realtime operations and agent customization</p><div className="cards"><div className="card">Service<br /><strong className="ok">{String(overview?.status)}</strong></div><div className="card">WhatsApp<br /><strong>{String(overview?.whatsapp_enabled)}</strong></div><div className="card">Providers<br /><strong>{String(overview?.providers)}</strong></div><div className="card">Agents<br /><strong>{String(overview?.agents)}</strong></div></div></>}
    {tab === "agents" && <div className="card"><h3>Agent Studio</h3><form onSubmit={saveAgent} className="form-grid"><label>ID<input className="input" value={agent.id} disabled={!!agent.revision} onChange={(e) => setAgent({ ...agent, id: e.target.value })} /></label><label>Name<input className="input" value={agent.name} onChange={(e) => setAgent({ ...agent, name: e.target.value })} /></label><label>System prompt<textarea className="input" value={agent.system_prompt} onChange={(e) => setAgent({ ...agent, system_prompt: e.target.value })} /></label><label>Tools (comma separated)<input className="input" value={agent.tools.join(",")} onChange={(e) => setAgent({ ...agent, tools: e.target.value.split(",").map((v) => v.trim()) })} /></label><label>Provider priority (IDs)<input className="input" value={agent.provider_ids.join(",")} onChange={(e) => setAgent({ ...agent, provider_ids: e.target.value.split(",").map((v) => v.trim()) })} /></label><button className="button">Save agent</button></form><hr />{agents.map((item) => <p key={item.id}><button className="link" onClick={() => setAgent(item)}>{item.name}</button> · revision {item.revision} <button className="danger" onClick={() => remove(`/dashboard/agents/${item.id}`, item.name)}>Delete</button></p>)}</div>}
    {tab === "providers" && <div className="card"><h3>Provider Manager</h3><form onSubmit={saveProvider} className="form-grid"><label>ID<input className="input" value={provider.id} disabled={!!provider.revision} onChange={(e) => setProvider({ ...provider, id: e.target.value })} /></label><label>Name<input className="input" value={provider.name} onChange={(e) => setProvider({ ...provider, name: e.target.value })} /></label><label>Type<select className="input" value={provider.type} onChange={(e) => setProvider({ ...provider, type: e.target.value })}><option value="ollama">Ollama</option><option value="openai_compatible">OpenAI compatible</option></select></label><label>Base URL<input className="input" value={provider.base_url} onChange={(e) => setProvider({ ...provider, base_url: e.target.value })} /></label><label>Model<input className="input" value={provider.model} onChange={(e) => setProvider({ ...provider, model: e.target.value })} /></label><label>Priority<input className="input" type="number" value={provider.priority} onChange={(e) => setProvider({ ...provider, priority: Number(e.target.value) })} /></label><label>Secret<input className="input" type="password" value={secret} placeholder={provider.has_secret ? "configured (leave blank to keep)" : ""} onChange={(e) => setSecret(e.target.value)} /></label><button className="button">Save provider</button>{provider.revision > 0 && <button type="button" className="button secondary" onClick={testProvider}>Test connection</button>}</form>{testResult && <p className="muted">{testResult}</p>}<hr />{providers.map((item) => <p key={item.id}><button className="link" onClick={() => setProvider(item)}>{item.name}</button> · {item.type} · {item.has_secret ? "secret configured" : "no secret"} <button className="danger" onClick={() => remove(`/dashboard/providers/${item.id}`, item.name)}>Delete</button></p>)}</div>}
    {tab === "chat" && <div className="card"><h3>Chat Console</h3><div className="conversation-list">{conversations.map((item) => <button className="link" key={item.id} onClick={() => void selectConversation(item.id)}>{item.title || item.id}</button>)}</div><div className="messages">{messages.map((item) => <p className={`message ${item.role}`} key={item.id}><strong>{item.role}:</strong> {item.content}</p>)}</div><form onSubmit={sendChat}><input className="input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Message your agent" /><button className="button" disabled={streaming}>{streaming ? "Waiting..." : "Send"}</button></form><div aria-live="polite">{streaming && "Waiting for provider response..."}</div></div>}
    {tab === "activity" && <div className="card"><h3>Live Activity</h3>{events.map((item, index) => <p key={`${String(item.id)}-${index}`}>{String(item.type)} · {String(item.correlation_id)}</p>)}</div>}
    {tab === "audit" && <div className="card"><h3>Audit Log</h3>{audit.length ? audit.map((item, index) => <p key={index}>{String(item.actor)} · {String(item.action)} · {String(item.resource)}</p>) : <p className="muted">No audit records.</p>}</div>}
  </section></div></main>;
}
