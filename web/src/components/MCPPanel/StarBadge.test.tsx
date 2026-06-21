import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StarBadge } from "./StarBadge";

describe("StarBadge", () => {
  it("muestra el count crudo cuando es < 1000", () => {
    render(<StarBadge stars={420} />);
    expect(screen.getByText("420")).toBeInTheDocument();
  });

  it("formatea a kilo (1 decimal) cuando es >= 1000", () => {
    render(<StarBadge stars={12345} />);
    expect(screen.getByText("12.3k")).toBeInTheDocument();
  });

  it("title del span incluye el count exacto", () => {
    const { container } = render(<StarBadge stars={420} />);
    const span = container.querySelector("span");
    expect(span?.getAttribute("title")).toBe("420 estrellas en GitHub");
  });

  it("snapshot de DOM estable", () => {
    const { container } = render(<StarBadge stars={2500} />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
