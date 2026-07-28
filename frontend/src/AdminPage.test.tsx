import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuditTable, ProgressEditor } from "./AdminPage";
import type { AdminGameDetail, AuditEvent } from "./api";

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
          photo: null,
          video: null,
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
          photo: null,
          video: null,
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

describe("admin audit trail", () => {
  it("shows the actor, activity, timestamp, and audit details", () => {
    const events: AuditEvent[] = [
      {
        id: "event-1",
        action: "clue.completed",
        entity_type: "clue",
        entity_id: "clue-1",
        reason: null,
        before: null,
        after: { game_id: "game-1", position: 2 },
        request_id: "request-1",
        created_at: "2026-07-28T14:35:00+00:00",
        actor: {
          id: "player-1",
          email_address: "player@example.com",
          full_name: "Player One",
          is_admin: false,
        },
        subject: null,
      },
    ];

    render(<AuditTable events={events} />);

    expect(screen.getByText("Player One")).toBeInTheDocument();
    expect(screen.getByText("Completed a clue")).toBeInTheDocument();
    expect(screen.getByText("Clue 2")).toBeInTheDocument();
    expect(screen.getByText("Jul 28, 2026, 10:35 AM")).toHaveAttribute(
      "datetime",
      events[0].created_at,
    );
    expect(screen.getByText("Record details")).toBeInTheDocument();
  });

  it("identifies unauthenticated failed logins without exposing an email", () => {
    const events: AuditEvent[] = [
      {
        id: "event-2",
        action: "auth.login_failed",
        entity_type: "login",
        entity_id: "hashed-identity",
        reason: "Invalid credentials",
        before: null,
        after: null,
        request_id: null,
        created_at: "2026-07-28T15:00:00+00:00",
        actor: null,
        subject: null,
      },
    ];

    render(<AuditTable events={events} />);

    expect(screen.getByText("Unknown account")).toBeInTheDocument();
    expect(screen.getByText("Sign-in rejected")).toBeInTheDocument();
    expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
  });
});
