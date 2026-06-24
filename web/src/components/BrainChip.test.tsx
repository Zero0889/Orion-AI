/**
 * Tests del chip indicador del cerebro activo.
 *
 * Lo que validamos:
 *   - No renderiza nada mientras la query carga (`data` es undefined).
 *   - Renderiza la label del provider cuando la query resuelve.
 *   - Click navega al SettingsPanel + dispara el evento `orion:settings:tab`
 *     con detail="brain" para que el panel salte a la pestaña correcta.
 *   - Estilo visual cambia con `is_live` (tono Gemini vs no-Gemini).
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BrainState } from "@/api/rest";
import { renderWithQuery } from "@/test/renderWithQuery";

vi.mock("@/api/rest", () => ({
  api: {
    getBrain: vi.fn(),
  },
}));

const setViewMock = vi.fn();
vi.mock("@/stores/view", () => ({
  useViewStore: (selector: (state: { setView: (v: string) => void }) => unknown) =>
    selector({ setView: setViewMock }),
}));

import { api } from "@/api/rest";
import { BrainChip } from "./BrainChip";

const mockedGetBrain = vi.mocked(api.getBrain);

function brainState(overrides: Partial<BrainState["active"]> = {}): BrainState {
  return {
    active: {
      provider: "gemini",
      model: "gemini-2.5-flash",
      is_live: true,
      ...overrides,
    },
    providers: [
      {
        id: "gemini",
        label: "Gemini",
        free: true,
        auth_hint: "x",
        models: [{ id: "gemini-2.5-flash", label: "Flash 2.5" }],
        default_model: "gemini-2.5-flash",
        available: true,
        needs_key: true,
      },
      {
        id: "deepseek",
        label: "DeepSeek",
        free: false,
        auth_hint: "x",
        models: [{ id: "deepseek-chat", label: "Chat" }],
        default_model: "deepseek-chat",
        available: true,
        needs_key: true,
      },
    ],
    ollama: { running: false, base_url: "http://localhost:11434", models: [] },
    gemini: { configured: true },
  };
}

describe("BrainChip", () => {
  beforeEach(() => {
    mockedGetBrain.mockReset();
    setViewMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("no renderiza nada antes del primer fetch", () => {
    mockedGetBrain.mockReturnValue(new Promise(() => {}));
    const { container } = renderWithQuery(<BrainChip />);
    expect(container.firstChild).toBeNull();
  });

  it("renderiza la label del provider activo cuando la query resuelve", async () => {
    mockedGetBrain.mockResolvedValue(brainState());
    renderWithQuery(<BrainChip />);
    await waitFor(() => expect(screen.getByRole("button")).toBeInTheDocument());
    expect(screen.getByText("Gemini")).toBeInTheDocument();
  });

  it("muestra el provider no-Gemini con su label", async () => {
    mockedGetBrain.mockResolvedValue(
      brainState({ provider: "deepseek", model: "deepseek-chat", is_live: false }),
    );
    renderWithQuery(<BrainChip />);
    await waitFor(() => expect(screen.getByText("DeepSeek")).toBeInTheDocument());
  });

  it("click abre Settings y dispara el evento custom de pestaña Cerebro", async () => {
    mockedGetBrain.mockResolvedValue(brainState());
    const handler = vi.fn();
    window.addEventListener("orion:settings:tab", handler);

    renderWithQuery(<BrainChip />);
    const btn = await screen.findByRole("button");
    fireEvent.click(btn);

    expect(setViewMock).toHaveBeenCalledWith("settings");
    expect(handler).toHaveBeenCalledTimes(1);
    expect((handler.mock.calls[0][0] as CustomEvent).detail).toBe("brain");

    window.removeEventListener("orion:settings:tab", handler);
  });

  it("aplica clases de borde distintas según is_live", async () => {
    mockedGetBrain.mockResolvedValue(
      brainState({ provider: "deepseek", model: "deepseek-chat", is_live: false }),
    );
    renderWithQuery(<BrainChip />);
    const btn = await screen.findByRole("button");
    // No es Live → borde warn (no pri).
    expect(btn.className).toMatch(/border-warn/);
    expect(btn.className).not.toMatch(/border-pri\b/);
  });
});
