"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_ORIGIN ?? "https://whatsappaiagent-production-63d3.up.railway.app";
type Item = Record<string, unknown>;

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${API}${path}`, { ...init, credentials: "include", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
  return response.json();
}

export default function Dashboard() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [overview, setOverview] = useState<Item | null>(null);
  const [agents, setAgents] = useState<Item[]>([]);
  const [providers, setProviders] = useState<Item[]>([]);
  const [audit, setAudit] = useState<Item[]>([]);
  const [events, setEvents] = useState<Item[]>([]);
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [tab, setTab] = useState("overview");

  async function load() {
    const [summary, agentData, providerData, auditData, eventData] = await Promise.all([
      request("/dashboard/overview"), request("/dashboard/agents"), request("/dashboard/providers"),
      request("/dashboard/audit"), request("/dashboard/events"),
    ]);
    setOverview(summary); setAgents(agentData.agents); setProviders(providerData.providers);
    setAudit(auditData.audit); setEvents(eventData.events);
  }

  useEffect(() => {
    request("/dashboard/overview").then((data) => { setOverview(data); setAuthenticated(true); return load(); })
      .catch((cause: Error) => { setAuthenticated(false); setError(cause.message); });
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const source = new EventSource(`${API}/dashboard/events/stream`, { withCredentials: true });
    source.onmessage = (event) => setEvents((current) => [JSON.parse(event.data), ...current].slice(0, 100));
    source.onerror = () => setError("Live activity stream disconnected; existing events remain available.");
    return () => source.close();
  }, [authenticated]);

  async function login(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); setAuthenticated(true); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Login failed"); }
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault(); if (!message.trim()) return;
    try { const result = await request("/dashboard/chat", { method: "POST", body: JSON.stringify({ text: message }) }); setReply(JSON.stringify(result, null, 2)); setMessage(""); }
    catch (cause) { setReply(cause instanceof Error ? cause.message : "Chat failed"); }
  }

  async function logout() { await request("/auth/logout", { method: "POST" }); setAuthenticated(false); }

  if (authenticated === null) return <main><p className="muted">Connecting to control center...</p></main>;
  if (!authenticated) return <main><form className="login card" onSubmit={login}><h1>Agent Control Center</h1><p className="muted">Sign in to manage your agent.</p>{error && <p className="bad">{error}</p>}<input className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" /><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" /><button className="button">Sign in</button></form></main>;

  return <main><div className="shell"><nav className="nav"><h1>Agent Control Center</h1>{["overview", "chat", "agents", "providers", "activity", "audit"].map((name) => <button className="navlink" key={name} onClick={() => setTab(name)}>{name}</button>)}<button className="navlink" onClick={logout}>Sign out</button></nav><section><h2>Personal AI Workspace</h2>{error && <p className="bad">{error}</p>}
    {tab === "overview" && <><p className="muted">Realtime operations and agent customization</p><div className="cards"><div className="card">Service<br /><strong className="ok">{String(overview?.status)}</strong></div><div className="card">WhatsApp<br /><strong>{String(overview?.whatsapp_enabled)}</strong></div><div className="card">Providers<br /><strong>{String(overview?.providers)}</strong></div><div className="card">Agents<br /><strong>{String(overview?.agents)}</strong></div></div></>}
    {tab === "chat" && <div className="card"><h3>Chat Console</h3><form onSubmit={sendChat}><input className="input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Message your agent" /><button className="button">Send</button></form><pre>{reply}</pre></div>}
    {tab === "agents" && <div className="card"><h3>Agents</h3>{agents.length ? agents.map((item) => <p key={String(item.id)}><strong>{String(item.name)}</strong> · {String(item.response_language)} · revision {String(item.revision)}</p>) : <p className="muted">No agents configured.</p>}</div>}
    {tab === "providers" && <div className="card"><h3>Providers</h3>{providers.length ? providers.map((item) => <p key={String(item.id)}><strong>{String(item.name)}</strong> · {String(item.type)} · {item.has_secret ? "secret configured" : "no secret"}</p>) : <p className="muted">No providers configured.</p>}</div>}
    {tab === "activity" && <div className="card"><h3>Live Activity</h3>{events.map((item, index) => <p key={`${String(item.id)}-${index}`}>{String(item.type)} · {String(item.correlation_id)}</p>)}</div>}
    {tab === "audit" && <div className="card"><h3>Audit Log</h3>{audit.length ? audit.map((item, index) => <p key={index}>{String(item.actor)} · {String(item.action)} · {String(item.resource)}</p>) : <p className="muted">No audit records.</p>}</div>}
  </section></div></main>;
}
