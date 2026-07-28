import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ClueMediaAttachments, CurrentClueCard } from "./PlayerPage";

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
