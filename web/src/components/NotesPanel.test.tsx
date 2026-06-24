/**
 * Smoke test del POC de TanStack Query en NotesPanel.
 *
 * No intenta cubrir todo el panel (edit/pin/delete/composer) — sólo
 * valida que:
 *  - Bajo un QueryClientProvider con `api.listNotes` mockeado, las notas
 *    pintan después del primer fetch.
 *  - El estado vacío se muestra si la query resuelve [].
 *  - El error del query no rompe el render (sólo dispara toast).
 *
 * Cuando se migren los otros 7 paneles, replicar este patrón: mock de
 * api.X(), render con `renderWithQuery`, asertar contenido + estados.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NoteApi } from "@/api/rest";
import { renderWithQuery } from "@/test/renderWithQuery";

// Mocks de los módulos que NotesPanel toca via import. Usar vi.mock antes
// del import del componente para que vitest sustituya las exports.
vi.mock("@/api/rest", () => ({
  api: {
    listNotes: vi.fn(),
    createNote: vi.fn(),
    updateNote: vi.fn(),
    deleteNote: vi.fn(),
  },
}));

vi.mock("@/stores/toast", () => ({
  toast: {
    success: vi.fn(),
    info: vi.fn(),
    error: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}));

import { api } from "@/api/rest";
import { NotesPanel } from "./NotesPanel";

const mockedListNotes = vi.mocked(api.listNotes);

describe("NotesPanel (TanStack Query POC)", () => {
  beforeEach(() => {
    mockedListNotes.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza las notas devueltas por api.listNotes", async () => {
    const notes: NoteApi[] = [
      {
        id: "1",
        text: "Comprar pan",
        pinned: false,
        created: "2026-01-01T10:00:00",
        updated: "2026-01-01T10:00:00",
      },
      {
        id: "2",
        text: "Llamar a mamá",
        pinned: true,
        created: "2026-01-02T11:00:00",
        updated: "2026-01-02T11:00:00",
      },
    ];
    mockedListNotes.mockResolvedValue(notes);

    renderWithQuery(<NotesPanel />);

    await waitFor(() => {
      expect(screen.getByText("Comprar pan")).toBeInTheDocument();
      expect(screen.getByText("Llamar a mamá")).toBeInTheDocument();
    });
    expect(mockedListNotes).toHaveBeenCalledOnce();
  });

  it("muestra estado vacío cuando la lista resuelve []", async () => {
    mockedListNotes.mockResolvedValue([]);

    renderWithQuery(<NotesPanel />);

    await waitFor(() => {
      expect(screen.getByText(/aún no anoté nada/i)).toBeInTheDocument();
    });
  });

  it("no crashea cuando la query rechaza", async () => {
    mockedListNotes.mockRejectedValue(new Error("backend caído"));

    renderWithQuery(<NotesPanel />);

    // El composer sigue renderizado aunque la query haya fallado.
    expect(screen.getByPlaceholderText(/nueva nota/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockedListNotes).toHaveBeenCalled();
    });
  });
});
