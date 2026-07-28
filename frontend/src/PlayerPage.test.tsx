import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CurrentClueCard } from "./PlayerPage";

describe("current clue card", () => {
  it("presents the active clue as the primary action area", () => {
    const onCodeChange = vi.fn();
    const onSubmit = vi.fn();

    render(
      <CurrentClueCard
        current={{
          id: "clue-2",
          position: 2,
          status: "current",
          clue: "Look beneath the town clock",
        }}
        clueCount={5}
        code=""
        busy={false}
        error={null}
        onCodeChange={onCodeChange}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText("Current clue")).toBeInTheDocument();
    expect(screen.getByText("Clue 2 of 5")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Look beneath the town clock" }),
    ).toHaveClass("unlock-card__clue");

    fireEvent.change(screen.getByLabelText("Code for clue 2"), {
      target: { value: "CLOCK" },
    });
    expect(onCodeChange).toHaveBeenCalledWith("CLOCK");
  });
});
