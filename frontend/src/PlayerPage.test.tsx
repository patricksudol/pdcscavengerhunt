import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClueDetailCard, ClueList, ClueMediaAttachments } from "./PlayerPage";

afterEach(cleanup);

describe("clue detail card", () => {
  it("presents a selected available clue as the primary action area", () => {
    const onCodeChange = vi.fn();
    const onSubmit = vi.fn();

    render(
      <ClueDetailCard
        clue={{
          id: "clue-2",
          position: 2,
          status: "available",
          clue: "Look beneath the town clock",
        }}
        clueCount={5}
        gameStatus="open"
        code=""
        busy={false}
        error={null}
        onCodeChange={onCodeChange}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText("Your selected clue")).toBeInTheDocument();
    expect(screen.getByText("Clue 2 of 5")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Look beneath the town clock" }),
    ).toHaveClass("unlock-card__clue");

    fireEvent.change(screen.getByLabelText("Code for clue 2"), {
      target: { value: "CLOCK" },
    });
    expect(onCodeChange).toHaveBeenCalledWith("CLOCK");
  });

  it("shows the revealed answer instead of a code form for a solved clue", () => {
    render(
      <ClueDetailCard
        clue={{
          id: "clue-1",
          position: 1,
          status: "completed",
          clue: "Start at the clock",
          answer: "Walk to the clock.",
        }}
        clueCount={2}
        gameStatus="open"
        code=""
        busy={false}
        error={null}
        onCodeChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("Clue solved")).toBeInTheDocument();
    expect(screen.getByText("Walk to the clock.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Solve clue" })).not.toBeInTheDocument();
  });
});

describe("clue list", () => {
  it("shows thin selectable rows for every clue and marks solved clues", () => {
    render(
      <ClueList
        gameId="game-1"
        clues={[
          {
            id: "clue-1",
            position: 1,
            status: "available",
            clue: "Find the clock",
          },
          {
            id: "clue-2",
            position: 2,
            status: "completed",
            clue: "Spot the mural",
            answer: "The blue wall",
          },
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: /Clue 1 Find the clock View clue/ }))
      .toHaveAttribute("href", "/games/game-1/clues/clue-1");
    expect(screen.getByRole("link", { name: /Clue 2 Spot the mural Solved/ }))
      .toHaveAttribute("href", "/games/game-1/clues/clue-2");
  });
});

describe("clue media attachments", () => {
  it("renders a playable photo and video", () => {
    render(
      <ClueMediaAttachments
        clueTitle="Town clock"
        photo={{
          id: "photo-1",
          media_type: "photo",
          content_type: "image/webp",
          size_bytes: 2048,
          status: "ready",
          url: "/api/v1/media/photo-1",
        }}
        video={{
          id: "video-1",
          media_type: "video",
          content_type: "video/mp4",
          size_bytes: 4096,
          status: "ready",
          url: "/api/v1/media/video-1",
        }}
      />,
    );

    expect(screen.getByRole("img", { name: "Photo for Town clock" })).toHaveAttribute(
      "src",
      "/api/v1/media/photo-1",
    );
    expect(
      screen.getByLabelText("Video for Town clock"),
    ).toHaveAttribute("src", "/api/v1/media/video-1");
  });
});
