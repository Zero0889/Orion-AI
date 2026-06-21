import { describe, expect, it } from "vitest";

import type { IoTDevice } from "@/api/rest";

import { isObj, kindFromDevice, slugify } from "./constants";

describe("slugify", () => {
  it("normaliza acentos y espacios a underscore lowercase", () => {
    expect(slugify("  Foco Salón Principal  ")).toBe("foco_salon_principal");
  });

  it("colapsa runs de no-alfanuméricos a un solo underscore", () => {
    expect(slugify("light---01 // beta")).toBe("light_01_beta");
  });

  it("trimea underscores de borde", () => {
    expect(slugify("___test___")).toBe("test");
  });

  it("trunca a 32 chars", () => {
    const long = "a".repeat(100);
    expect(slugify(long)).toHaveLength(32);
  });

  it("string vacío → vacío (no crashea)", () => {
    expect(slugify("")).toBe("");
  });
});

describe("kindFromDevice", () => {
  function mkDevice(over: Partial<IoTDevice> = {}): IoTDevice {
    return {
      id: "x",
      name: "x",
      transport: "mqtt",
      capabilities: { on_off: false, dimmable: false, rgb: false, sensor: null },
      ...over,
    };
  }

  it("respeta el kind explícito del usuario por encima de cualquier heurística", () => {
    const d = mkDevice({
      capabilities: { on_off: false, dimmable: false, rgb: false, sensor: "temperature" },
    });
    expect(kindFromDevice(d, { kind: "mixed" })).toBe("mixed");
  });

  it("sin device → default light", () => {
    expect(kindFromDevice(undefined)).toBe("light");
  });

  it("sensor capability → sensor", () => {
    const d = mkDevice({
      capabilities: { on_off: false, dimmable: false, rgb: false, sensor: "temperature" },
    });
    expect(kindFromDevice(d)).toBe("sensor");
  });

  it("rgb o dimmable → light", () => {
    const rgb = mkDevice({
      capabilities: { on_off: true, dimmable: false, rgb: true, sensor: null },
    });
    expect(kindFromDevice(rgb)).toBe("light");
    const dim = mkDevice({
      capabilities: { on_off: true, dimmable: true, rgb: false, sensor: null },
    });
    expect(kindFromDevice(dim)).toBe("light");
  });

  it("solo on_off + nombre tipo 'foco' → light por heurística LIGHT_HINTS", () => {
    const d = mkDevice({
      name: "Foco principal",
      capabilities: { on_off: true, dimmable: false, rgb: false, sensor: null },
    });
    expect(kindFromDevice(d)).toBe("light");
  });

  it("solo on_off + nombre neutro → switch", () => {
    const d = mkDevice({
      name: "Relay 03",
      id: "relay_03",
      capabilities: { on_off: true, dimmable: false, rgb: false, sensor: null },
    });
    expect(kindFromDevice(d)).toBe("switch");
  });

  it("ninguna capability conocida → mixed", () => {
    const d = mkDevice({
      capabilities: { on_off: false, dimmable: false, rgb: false, sensor: null },
    });
    expect(kindFromDevice(d)).toBe("mixed");
  });
});

describe("isObj", () => {
  it("true para objetos plain", () => {
    expect(isObj({})).toBe(true);
    expect(isObj({ a: 1 })).toBe(true);
  });

  it("false para null / primitivos / arrays gris — arrays son objetos en JS", () => {
    expect(isObj(null)).toBe(false);
    expect(isObj(undefined)).toBe(false);
    expect(isObj(42)).toBe(false);
    expect(isObj("hola")).toBe(false);
    expect(isObj(true)).toBe(false);
    expect(isObj([])).toBe(true);
  });
});
