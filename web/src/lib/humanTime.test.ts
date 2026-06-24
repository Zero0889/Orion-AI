import { describe, expect, it } from "vitest";

import { humanizeAge, humanizeTime, humanizeUnix } from "./humanTime";

const NOW = new Date("2026-06-21T14:30:00");

describe("humanizeTime", () => {
  it("returns 'ahora' for events within last 30 seconds", () => {
    expect(humanizeTime(new Date("2026-06-21T14:29:50"), NOW)).toBe("ahora");
    expect(humanizeTime(new Date("2026-06-21T14:30:00"), NOW)).toBe("ahora");
  });

  it("returns 'hace N min' for sub-hour events", () => {
    expect(humanizeTime(new Date("2026-06-21T14:25:00"), NOW)).toBe("hace 5 min");
    expect(humanizeTime(new Date("2026-06-21T13:31:00"), NOW)).toBe("hace 59 min");
  });

  it("returns 'hace N h' for same-day events older than 1h", () => {
    expect(humanizeTime(new Date("2026-06-21T12:30:00"), NOW)).toBe("hace 2 h");
    expect(humanizeTime(new Date("2026-06-21T02:30:00"), NOW)).toBe("hace 12 h");
  });

  it("returns 'ayer HH:MM' for yesterday's events", () => {
    expect(humanizeTime(new Date("2026-06-20T22:14:00"), NOW)).toBe("ayer 22:14");
    expect(humanizeTime(new Date("2026-06-20T08:05:00"), NOW)).toBe("ayer 08:05");
  });

  it("returns 'weekday DD mon' for events within the week", () => {
    expect(humanizeTime(new Date("2026-06-16T10:00:00"), NOW)).toBe("mar 16 jun");
    expect(humanizeTime(new Date("2026-06-15T22:00:00"), NOW)).toBe("lun 15 jun");
  });

  it("returns 'DD mon' for older events this year", () => {
    expect(humanizeTime(new Date("2026-03-04T09:00:00"), NOW)).toBe("4 mar");
  });

  it("includes year for prior-year events", () => {
    expect(humanizeTime(new Date("2024-11-30T09:00:00"), NOW)).toBe("30 nov 2024");
  });

  it("accepts epoch milliseconds and parseable strings", () => {
    expect(humanizeTime(new Date("2026-06-21T14:25:00").getTime(), NOW)).toBe("hace 5 min");
    expect(humanizeTime("2026-06-21T14:25:00", NOW)).toBe("hace 5 min");
  });

  it("returns em-dash for unparseable input", () => {
    expect(humanizeTime("no es fecha", NOW)).toBe("—");
    expect(humanizeTime(Number.NaN, NOW)).toBe("—");
  });

  it("falls back to HH:MM when event is in the future", () => {
    expect(humanizeTime(new Date("2026-06-21T16:05:00"), NOW)).toBe("16:05");
  });
});

describe("humanizeUnix", () => {
  it("converts UNIX seconds to humanized output", () => {
    const sec = Math.floor(new Date("2026-06-21T13:30:00").getTime() / 1000);
    expect(humanizeUnix(sec, NOW)).toBe("hace 1 h");
  });
});

describe("humanizeAge", () => {
  it("uses 'ahora' inside the noise window", () => {
    expect(humanizeAge(new Date("2026-06-21T14:29:58"), NOW)).toBe("ahora");
  });

  it("uses seconds resolution under a minute", () => {
    expect(humanizeAge(new Date("2026-06-21T14:29:50"), NOW)).toBe("hace 10 s");
  });

  it("scales up to minutes, hours, days (each unit rolls over at the threshold)", () => {
    expect(humanizeAge(new Date("2026-06-21T13:25:00"), NOW)).toBe("hace 1 h"); // 65 min
    expect(humanizeAge(new Date("2026-06-20T14:30:00"), NOW)).toBe("hace 1 d"); // 24 h
    expect(humanizeAge(new Date("2026-06-18T14:30:00"), NOW)).toBe("hace 3 d");
  });
});
