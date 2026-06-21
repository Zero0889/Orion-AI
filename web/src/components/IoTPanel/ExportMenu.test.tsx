import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ExportMenu } from "./ExportMenu";

describe("ExportMenu", () => {
  it("arranca cerrado — no muestra opciones de descarga", () => {
    render(<ExportMenu />);
    expect(screen.queryByText(/Excel \(\.xlsx\)/i)).toBeNull();
    expect(screen.queryByText(/CSV \(\.csv\)/i)).toBeNull();
  });

  it("abre el menú al click en el trigger", async () => {
    const user = userEvent.setup();
    render(<ExportMenu />);
    await user.click(screen.getByRole("button", { name: /exportar/i }));
    expect(screen.getByText(/Excel \(\.xlsx\)/i)).toBeInTheDocument();
    expect(screen.getByText(/CSV \(\.csv\)/i)).toBeInTheDocument();
  });

  it("los links apuntan a los endpoints REST de descarga", async () => {
    const user = userEvent.setup();
    render(<ExportMenu />);
    await user.click(screen.getByRole("button", { name: /exportar/i }));

    const xlsx = screen.getByText(/Excel \(\.xlsx\)/i).closest("a");
    const csv = screen.getByText(/CSV \(\.csv\)/i).closest("a");

    expect(xlsx?.getAttribute("href")).toBe("/api/iot/sensor_log/xlsx");
    expect(xlsx?.hasAttribute("download")).toBe(true);
    expect(csv?.getAttribute("href")).toBe("/api/iot/sensor_log/csv");
    expect(csv?.hasAttribute("download")).toBe(true);
  });

  it("click fuera del menú lo cierra", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <ExportMenu />
        <div data-testid="outside">soy de afuera</div>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: /exportar/i }));
    expect(screen.getByText(/Excel \(\.xlsx\)/i)).toBeInTheDocument();

    await user.click(screen.getByTestId("outside"));
    expect(screen.queryByText(/Excel \(\.xlsx\)/i)).toBeNull();
  });

  it("click sobre una opción cierra el menú", async () => {
    const user = userEvent.setup();
    render(<ExportMenu />);
    await user.click(screen.getByRole("button", { name: /exportar/i }));
    await user.click(screen.getByText(/CSV \(\.csv\)/i));
    expect(screen.queryByText(/Excel \(\.xlsx\)/i)).toBeNull();
  });
});
