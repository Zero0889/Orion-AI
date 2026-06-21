import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { IoTDevice } from "@/api/rest";

import { CapChip, NumInput, QuickPick, ReadOnlyBackendBadges } from "./controls";

describe("NumInput", () => {
  // NumInput es controlado: `value` viene por prop. Para testear la lógica
  // de clamp sin construir un harness con state, usamos fireEvent.change
  // directo, que dispara un único onChange con el value que queramos.

  it("clampea al min cuando el value entrante es menor", () => {
    const onChange = vi.fn();
    render(<NumInput value={50} onChange={onChange} min={10} max={100} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "5" } });
    expect(onChange).toHaveBeenLastCalledWith(10);
  });

  it("clampea al max cuando el value entrante es mayor", () => {
    const onChange = vi.fn();
    render(<NumInput value={50} onChange={onChange} min={0} max={20} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "999" } });
    expect(onChange).toHaveBeenLastCalledWith(20);
  });

  it("permite valores dentro del rango sin clampear", () => {
    const onChange = vi.fn();
    render(<NumInput value={50} onChange={onChange} min={0} max={100} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "42" } });
    expect(onChange).toHaveBeenLastCalledWith(42);
  });

  it("vaciar el input emite 0 (sin NaN)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<NumInput value={42} onChange={onChange} />);
    await user.clear(screen.getByRole("spinbutton"));
    expect(onChange).toHaveBeenLastCalledWith(0);
  });
});

describe("QuickPick", () => {
  it("dispara onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<QuickPick active={false} onClick={onClick} label="30s" />);
    await user.click(screen.getByRole("button", { name: "30s" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("active=true aplica la clase de estado activo (bg-pri/15)", () => {
    render(<QuickPick active={true} onClick={() => {}} label="1m" />);
    const btn = screen.getByRole("button", { name: "1m" });
    expect(btn.className).toContain("bg-pri/15");
  });
});

describe("CapChip", () => {
  it("disabled bloquea el onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<CapChip label="dim" active={false} disabled onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: /dim/i }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("enabled + click dispara onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<CapChip label="rgb" active={false} onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: /rgb/i }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("ReadOnlyBackendBadges", () => {
  const device: IoTDevice = {
    id: "x",
    name: "x",
    transport: "mqtt",
    capabilities: { on_off: true, dimmable: true, rgb: false, sensor: "temperature" },
  };

  it("no renderiza nada cuando mode != edit-backend", () => {
    const { container } = render(<ReadOnlyBackendBadges device={device} mode="create" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("no renderiza nada cuando device es undefined", () => {
    const { container } = render(<ReadOnlyBackendBadges device={undefined} mode="edit-backend" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renderiza solo las capabilities activas en modo edit-backend", () => {
    render(<ReadOnlyBackendBadges device={device} mode="edit-backend" />);
    expect(screen.getByText("on/off")).toBeInTheDocument();
    expect(screen.getByText("dim")).toBeInTheDocument();
    expect(screen.queryByText("rgb")).toBeNull();
    expect(screen.getByText(/sensor · temperature/)).toBeInTheDocument();
  });
});
