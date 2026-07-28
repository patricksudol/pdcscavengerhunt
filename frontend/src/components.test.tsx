import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Brand, StatusBadge } from "./components";

describe("shared interface", () => {
  it("renders the PDC scavenger hunt brand", () => {
    render(<Brand />);
    expect(screen.getByText("Phoenixville Democrats")).toBeInTheDocument();
    expect(screen.getByText("Scavenger Hunt")).toBeInTheDocument();
  });

  it("renders a readable game status", () => {
    render(<StatusBadge status="open" />);
    expect(screen.getByText("open")).toHaveClass("status--open");
  });
});
