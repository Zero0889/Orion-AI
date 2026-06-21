import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  agentIconTone,
  createSession,
  loadSessions,
  saveSessions,
  useProviderLabel,
  type AgentSessions,
} from "./types";

describe("agentIconTone", () => {
  it("devuelve la clase tailwind del catálogo", () => {
    expect(agentIconTone("compass")).toBe("text-amber-400");
    expect(agentIconTone("code")).toBe("text-emerald-400");
  });

  it("fallback text-pri cuando el ícono no está mapeado", () => {
    expect(agentIconTone("inexistente")).toBe("text-pri");
  });
});

describe("useProviderLabel", () => {
  it("mapea ids conocidos a labels humanos", () => {
    expect(useProviderLabel("gemini")).toBe("Gemini");
    expect(useProviderLabel("anthropic")).toBe("Claude");
    expect(useProviderLabel("ollama_cloud")).toBe("Ollama Cloud");
  });

  it("fallback al id raw cuando es desconocido", () => {
    expect(useProviderLabel("nuevo_provider")).toBe("nuevo_provider");
  });
});

describe("createSession", () => {
  it("genera id único y messages vacío", () => {
    const a = createSession("Chat 1");
    const b = createSession("Chat 2");
    expect(a.id).not.toBe(b.id);
    expect(a.id).toMatch(/^s_\d+_[a-z0-9]{6}$/);
    expect(a.title).toBe("Chat 1");
    expect(a.messages).toEqual([]);
    expect(a.createdAt).toBeGreaterThan(0);
  });
});

describe("loadSessions / saveSessions (localStorage)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("loadSessions devuelve {} cuando no hay nada persistido", () => {
    expect(loadSessions()).toEqual({});
  });

  it("loadSessions devuelve {} y no crashea cuando el blob es JSON inválido", () => {
    window.localStorage.setItem("orion.agent.sessions", "{not-json");
    expect(loadSessions()).toEqual({});
  });

  it("saveSessions persiste y loadSessions lee el mismo objeto", () => {
    const data: AgentSessions = {
      "agent-x": [createSession("Saludo")],
    };
    saveSessions(data);
    const round = loadSessions();
    expect(round["agent-x"]).toHaveLength(1);
    expect(round["agent-x"][0].title).toBe("Saludo");
  });

  it("saveSessions descarta agentes con array vacío (no mete ruido)", () => {
    saveSessions({ "agent-x": [], "agent-y": [createSession("A")] });
    const round = loadSessions();
    expect(round).not.toHaveProperty("agent-x");
    expect(round["agent-y"]).toHaveLength(1);
  });

  it("saveSessions trunca cada sesión a los últimos 80 mensajes", () => {
    const sess = createSession("Long");
    sess.messages = Array.from({ length: 120 }, (_, i) => ({
      role: "user" as const,
      text: `msg-${i}`,
      ts: i,
    }));
    saveSessions({ a: [sess] });
    const round = loadSessions();
    expect(round.a[0].messages).toHaveLength(80);
    // Tail preserved: el último mensaje sigue siendo msg-119
    expect(round.a[0].messages.at(-1)?.text).toBe("msg-119");
  });
});
