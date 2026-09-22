"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export default function Dashboard() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [overview, setOverview] = useState<Record<string, unknown> | null>(null);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [text, setText] = useState("");
  const [reply, setReply] = useState("");

  useEffect(() => {
    fetch(`${API}/dashboard/overview`, { credentials: "include" })
      .then(async (response) => {
        setAuthenticated(response.ok);
        if (response.ok) setOverview(await response.json());
      });
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const source = new EventSource(`${API}/dashboard/events/stream`, { withCredentials: true });
    source.onmessage = (event) => setEvents((current) => [JSON.parse(event.data), ...current].slice(0, 50));
    return () => source.close();
  }, [authenticated]);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    const response = await fetch(`${API}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username, password}),
    });
    if (!response.ok) {
      setLoginError("Login failed");
      return;
    }
    setLoginError("");
    setAuthenticated(true);
  }

  async function sendChat() {
    const response = await fetch(`${API}/dashboard/chat`, { method: "POST", credentials: "include", headers: {"Content-Type":"application/json"}, body: JSON.stringify({text}) });
    setReply(response.ok ? JSON.stringify(await response.json()) : "Request failed");
  }

  if (authenticated === false) return <main><form className="login card" onSubmit={login}><h1>Agent Control Center</h1><p className="muted">Sign in to manage your agent.</p><input className="input" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" autoComplete="username" /><input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" autoComplete="current-password" /><button className="button" type="submit">Sign in</button>{loginError && <p>{loginError}</p>}</form></main>;
  if (authenticated === null) return <main><p className="muted">Loading control center...</p></main>;
  return <main><div className="shell"><nav className="nav"><h1>Agent Control Center</h1><a href="#overview">Overview</a><a href="#activity">Live Activity</a><a href="#chat">Chat Console</a><a href="#agents">Agents</a><a href="#providers">Providers</a><a href="#settings">Settings</a></nav><section><h2>Personal AI Workspace</h2><p className="muted">Realtime operations and agent customization</p><div id="overview" className="cards"><div className="card">Service<br/><strong className="ok">{String(overview?.status ?? "Loading")}</strong></div><div className="card">WhatsApp<br/><strong>{String(overview?.whatsapp_enabled ?? "Loading")}</strong></div><div className="card">Providers<br/><strong>{String(overview?.providers ?? 0)}</strong></div></div><div id="chat" className="card" style={{marginTop:14}}><h3>Chat Console</h3><input className="input" value={text} onChange={(event) => setText(event.target.value)} placeholder="Message your agent" /><button className="button" onClick={sendChat}>Send</button><pre>{reply}</pre></div><div id="activity" className="card" style={{marginTop:14}}><h3>Live Activity</h3>{events.length === 0 ? <p className="muted">No events yet</p> : events.map((event, index) => <div key={index}>{JSON.stringify(event)}</div>)}</div></section></div></main>;
}
