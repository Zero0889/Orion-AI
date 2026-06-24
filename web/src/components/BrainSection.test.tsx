/**
 * Tests del BrainSection.
 *
 * Foco: el snapshot de estado del cerebro se renderiza correcto (cerebro
 * activo, providers, badge de Ollama detectado/ausente, aviso de voz si
 * el provider no es Gemini). No replicamos los mutation flows uno por
 * uno — esos están cubiertos por los tests del backend (test_brain_routes.py).
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BrainState } from "@/api/rest";
import { renderWithQuery } from "@/test/renderWithQuery";

vi.mock("@/api/rest", () => ({
  api: {
    getBrain: vi.fn(),
    setBrain: vi.fn(),
    setBrainProviderKey: vi.fn(),
    testBrain: vi.fn(),
  },
}));

vi.mock("@/stores/toast", () => ({
  toast: {
    success: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import { api } from "@/api/rest";
import { BrainSection } from "./BrainSection";

const mockedGetBrain = vi.mocked(api.getBrain);

function buildState(overrides: Partial<BrainState> = {}): BrainState {
  return {
    active: { provider: "gemini", model: "gemini-2.5-flash", is_live: true },
    providers: [
      {
        id: "gemini",
        label: "Gemini",
        free: true,
        auth_hint: "GOOGLE_API_KEY",
        models: [{ id: "gemini-2.5-flash", label: "Flash 2.5" }],
        default_model: "gemini-2.5-flash",
        available: true,
        needs_key: true,
      },
      {
        id: "deepseek",
        label: "DeepSeek",
        free: false,
        auth_hint: "DEEPSEEK_API_KEY",
        models: [{ id: "deepseek-chat", label: "Chat" }],
        default_model: "deepseek-chat",
        available: false,
        needs_key: true,
      },
      {
        id: "ollama",
        label: "Ollama (local)",
        free: true,
        auth_hint: "sin auth",
        models: [{ id: "llama3.1:8b", label: "Llama 3.1 8B" }],
        default_model: "llama3.1:8b",
        available: true,
        needs_key: false,
      },
    ],
    ollama: { running: false, base_url: "http://localhost:11434", models: [] },
    gemini: { configured: true },
    ...overrides,
  };
}

describe("BrainSection", () => {
  beforeEach(() => {
    mockedGetBrain.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("muestra el cerebro activo con su provider y modelo", async () => {
    mockedGetBrain.mockResolvedValue(buildState());
    renderWithQuery(<BrainSection />);
    await waitFor(() => expect(screen.getByText(/Cerebro activo/i)).toBeInTheDocument());
    expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument();
  });

  it("expone el badge 'Voz activa' cuando is_live + gemini.configured", async () => {
    mockedGetBrain.mockResolvedValue(buildState());
    renderWithQuery(<BrainSection />);
    // 'Voz activa' es único en la sección (no aparece en el copy
    // descriptivo). Sirve como prueba de que el badge se renderizó.
    await waitFor(() => expect(screen.getByText(/Voz activa/i)).toBeInTheDocument());
  });

  it("muestra el card de Ollama no detectado con link de instalación", async () => {
    mockedGetBrain.mockResolvedValue(
      buildState({
        active: { provider: "ollama", model: "llama3.1:8b", is_live: false },
      }),
    );
    renderWithQuery(<BrainSection />);
    await waitFor(() => expect(screen.getByText(/Ollama no detectado/i)).toBeInTheDocument());
    // Link a ollama.com/download presente
    const link = screen.getByRole("link", { name: /ollama.com\/download/i });
    expect(link).toHaveAttribute("href", "https://ollama.com/download");
  });

  it("muestra el aviso de voz cuando el cerebro no es Gemini", async () => {
    mockedGetBrain.mockResolvedValue(
      buildState({
        active: { provider: "deepseek", model: "deepseek-chat", is_live: false },
      }),
    );
    renderWithQuery(<BrainSection />);
    // El aviso menciona Gemini Live y que la voz necesita la key
    await waitFor(() =>
      expect(screen.getByText(/voz en tiempo real exige Gemini Live/i)).toBeInTheDocument(),
    );
  });

  it("renderiza error inline si la query falla", async () => {
    mockedGetBrain.mockRejectedValue(new Error("backend caído"));
    renderWithQuery(<BrainSection />);
    await waitFor(() => expect(screen.getByText(/No pude leer el cerebro/i)).toBeInTheDocument());
  });
});
