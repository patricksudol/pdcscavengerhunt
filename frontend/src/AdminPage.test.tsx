import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProgressEditor } from "./AdminPage";
import type { AdminGameDetail } from "./api";

afterEach(cleanup);

describe("admin player progress", () => {
  it("shows the completion time for each solved clue", () => {
    const game: AdminGameDetail = {
      id: "game-1",
      title: "Timestamp Hunt",
      description: null,
      instructions: null,
      closing_message: null,
      status: "open",
      player_count: 1,
      clue_count: 1,
      completion_count: 1,
      created_at: "2026-07-28T12:00:00+00:00",
      updated_at: "2026-07-28T12:00:00+00:00",
      clues: [
        {
          id: "clue-1",
          position: 1,
          title: "Find the mural",
          content: "At the corner of...",
          code: "MURAL",
          code_set: true,
        },
      ],
      players: [
        {
          membership_id: "membership-1",
          user: {
            id: "player-1",
            email_address: "player@example.com",
            full_name: "Player One",
            is_admin: false,
            active: true,
            password_set: true,
            created_at: "2026-07-28T12:00:00+00:00",
            last_login_at: null,
          },
          completed_count: 1,
          completed_clue_ids: ["clue-1"],
          completion_rank: 1,
          finished_at: "2026-07-28T14:35:00+00:00",
          completions: [
            {
              clue_id: "clue-1",
              completed_at: "2026-07-28T14:35:00+00:00",
            },
          ],
        },
      ],
    };

    render(<ProgressEditor game={game} />);

    expect(screen.getByText("Find the mural")).toBeInTheDocument();
    expect(screen.getByText("Jul 28, 2026, 10:35 AM")).toHaveAttribute(
      "datetime",
      "2026-07-28T14:35:00+00:00",
    );
    expect(screen.getByLabelText("1st place")).toHaveClass("finish-rank--gold");
  });

  it("uses medal treatments for the top three and ranks every other finisher", () => {
    const player = {
      membership_id: "membership-1",
      user: {
        id: "player-1",
        email_address: "player@example.com",
        full_name: "Player One",
        is_admin: false,
        active: true,
        password_set: true,
        created_at: "2026-07-28T12:00:00+00:00",
        last_login_at: null,
      },
      completed_count: 1,
      completed_clue_ids: ["clue-1"],
      completion_rank: 1,
      finished_at: "2026-07-28T14:35:00+00:00",
      completions: [
        {
          clue_id: "clue-1",
          completed_at: "2026-07-28T14:35:00+00:00",
        },
      ],
    };
    const game: AdminGameDetail = {
      id: "game-1",
      title: "Ranked Hunt",
      description: null,
      instructions: null,
      closing_message: null,
      status: "open",
      player_count: 4,
      clue_count: 1,
      completion_count: 4,
      created_at: "2026-07-28T12:00:00+00:00",
      updated_at: "2026-07-28T12:00:00+00:00",
      clues: [
        {
          id: "clue-1",
          position: 1,
          title: "Final clue",
          content: "The finish",
          code: "FINISH",
          code_set: true,
        },
      ],
      players: [1, 2, 3, 4].map((rank) => ({
        ...player,
        membership_id: `membership-${rank}`,
        user: {
          ...player.user,
          id: `player-${rank}`,
          email_address: `player${rank}@example.com`,
          full_name: `Player ${rank}`,
        },
        completion_rank: rank,
      })),
    };

    render(<ProgressEditor game={game} />);

    expect(screen.getByLabelText("1st place")).toHaveClass("finish-rank--gold");
    expect(screen.getByLabelText("2nd place")).toHaveClass("finish-rank--silver");
    expect(screen.getByLabelText("3rd place")).toHaveClass("finish-rank--bronze");
    expect(screen.getByLabelText("4th place")).toHaveClass("finish-rank--numbered");
  });
});
