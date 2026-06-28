/**
 * Smoke tests del AccessPanel top-level (Fase 5).
 *
 * Cubre el orquestador con 3 queries (users / events / daily), 3 tabs,
 * y los enlaces de export. NO repite los tests de las sub-tabs
 * (DailyReportTab / EventsTab / UsersTab), que viven aparte cuando se
 * agreguen — acá solo verificamos que el shell coordina bien.
 *
 * Patrón establecido en NotesPanel.test.tsx: vi.mock de @/api/rest +
 * @/stores/toast antes del import del componente, renderWithQuery con
 * QueryClient fresco por test.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AccessDailyRow, AccessEventsPage, AccessUser } from "@/api/rest";
import { renderWithQuery } from "@/test/renderWithQuery";

vi.mock("@/api/rest", () => ({
  api: {
    accessUsers: vi.fn(),
    accessListEvents: vi.fn(),
    accessDaily: vi.fn(),
    accessCreateUser: vi.fn(),
    accessUpdateUser: vi.fn(),
    accessDeleteUser: vi.fn(),
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

// inferBackendUrl es trivial (lee window.location) — mockeo a algo
// determinístico para los hrefs de export.
vi.mock("@/api/ws", () => ({
  inferBackendUrl: () => ({ http: "http://localhost:8765", ws: "ws://localhost:8765" }),
}));

import { api } from "@/api/rest";

import { AccessPanel } from "./index";

const mockedUsers = vi.mocked(api.accessUsers);
const mockedListEvents = vi.mocked(api.accessListEvents);
const mockedDaily = vi.mocked(api.accessDaily);

const SAMPLE_USERS: AccessUser[] = [
  {
    id: "u1",
    fingerprint_id: 1,
    name: "Zahir Test",
    phone: "+51 999",
    active: true,
    created: "2026-06-28T10:00:00",
  },
  {
    id: "u2",
    fingerprint_id: 12,
    name: "María Test",
    phone: "",
    active: false,
    created: "2026-06-28T11:00:00",
  },
];

const SAMPLE_EVENTS_PAGE: AccessEventsPage = {
  items: [
    {
      id: "e1",
      fingerprint_id: 1,
      event_type: "GRANTED",
      esp_id: "puerta",
      confidence: 150,
      timestamp: "2026-06-28T08:00:00-05:00",
      user_name: "Zahir Test",
    },
  ],
  total: 4,
  limit: 200,
  offset: 0,
};

const SAMPLE_DAILY: AccessDailyRow[] = [
  {
    fingerprint_id: 1,
    name: "Zahir Test",
    fecha: "2026-06-28",
    entrada: "08:00",
    salida: "16:58",
    tiempo_minutos: 538,
    tiempo_legible: "8 h 58 min",
    eventos_dia: 5,
  },
];

beforeEach(() => {
  mockedUsers.mockReset();
  mockedListEvents.mockReset();
  mockedDaily.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AccessPanel — orquestador", () => {
  it("muestra los badges con counts de las 3 queries", async () => {
    mockedUsers.mockResolvedValue(SAMPLE_USERS);
    mockedListEvents.mockResolvedValue(SAMPLE_EVENTS_PAGE);
    mockedDaily.mockResolvedValue(SAMPLE_DAILY);

    renderWithQuery(<AccessPanel />);

    await waitFor(() => {
      expect(screen.getByText("2 enrolados")).toBeInTheDocument();
      expect(screen.getByText("4 eventos")).toBeInTheDocument();
    });
    expect(mockedUsers).toHaveBeenCalledOnce();
    expect(mockedListEvents).toHaveBeenCalledWith({ limit: 200 });
    expect(mockedDaily).toHaveBeenCalledOnce();
  });

  it("renderiza la tab Reporte diario por default", async () => {
    mockedUsers.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    mockedDaily.mockResolvedValue(SAMPLE_DAILY);

    renderWithQuery(<AccessPanel />);

    // jsdom NO aplica media queries, así que tanto `md:hidden` (cards
    // mobile) como `hidden md:block` (tabla desktop) renderean — el
    // texto aparece 2 veces. Usamos findAllByText.
    const matches = await screen.findAllByText("8 h 58 min");
    expect(matches.length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zahir Test").length).toBeGreaterThan(0);
  });

  it("cambia a la tab Registros al clickearla", async () => {
    mockedUsers.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue(SAMPLE_EVENTS_PAGE);
    mockedDaily.mockResolvedValue([]);

    renderWithQuery(<AccessPanel />);

    // Las tabs aparecen en el header
    const tabRegistros = await screen.findByRole("button", { name: /registros/i });
    fireEvent.click(tabRegistros);

    await waitFor(() => {
      // EventsTab muestra "GRANTED" como Badge — verificamos su presencia
      expect(screen.getByText("GRANTED")).toBeInTheDocument();
    });
  });

  it("cambia a la tab Usuarios al clickearla", async () => {
    mockedUsers.mockResolvedValue(SAMPLE_USERS);
    mockedListEvents.mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    mockedDaily.mockResolvedValue([]);

    renderWithQuery(<AccessPanel />);

    const tabUsuarios = await screen.findByRole("button", { name: /usuarios/i });
    fireEvent.click(tabUsuarios);

    await waitFor(() => {
      // El header de la tab Usuarios muestra "2/128 slots ocupados"
      expect(screen.getByText(/2\/128 slots ocupados/i)).toBeInTheDocument();
    });
  });

  it("expone los enlaces de export XLSX y CSV con la URL del backend", async () => {
    mockedUsers.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    mockedDaily.mockResolvedValue([]);

    renderWithQuery(<AccessPanel />);

    const xlsxLink = await screen.findByTitle(/descargar reporte xlsx/i);
    const csvLink = screen.getByTitle(/descargar reporte csv/i);

    expect(xlsxLink).toHaveAttribute("href", "http://localhost:8765/api/access/export.xlsx");
    expect(csvLink).toHaveAttribute("href", "http://localhost:8765/api/access/export.csv");
    expect(xlsxLink).toHaveAttribute("target", "_blank");
  });

  it("muestra el banner de error si una query falla", async () => {
    mockedUsers.mockRejectedValue(new Error("backend caído"));
    mockedListEvents.mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    mockedDaily.mockResolvedValue([]);

    renderWithQuery(<AccessPanel />);

    await waitFor(() => {
      expect(screen.getByText(/backend caído/i)).toBeInTheDocument();
    });
  });

  it("muestra el empty state del reporte diario cuando no hay rows", async () => {
    mockedUsers.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    mockedDaily.mockResolvedValue([]);

    renderWithQuery(<AccessPanel />);

    await waitFor(() => {
      expect(screen.getByText(/sin registros todavía/i)).toBeInTheDocument();
    });
  });
});
