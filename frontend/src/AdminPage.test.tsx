import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AuditTable,
  GameEditor,
  HintsEditor,
  Players,
  ProgressEditor,
} from "./AdminPage";
import type {
  AdminClue,
  AdminGameDetail,
  AdminUser,
  AuditEvent,
  Me,
} from "./api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
  } as Response;
}

describe("admin player accounts", () => {
  it("confirms and permanently deletes another user", async () => {
    const me: Me = {
      id: "admin-1",
      email_address: "admin@example.com",
      full_name: "Admin User",
      is_admin: true,
      csrf_token: "csrf",
    };
    const users: AdminUser[] = [
      {
        id: "player-1",
        email_address: "player@example.com",
        full_name: "Player One",
        is_admin: false,
        active: true,
        password_set: true,
        game_count: 2,
        created_at: "2026-07-28T12:00:00+00:00",
        last_login_at: null,
      },
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === "/api/v1/admin/users" && (!init?.method || init.method === "GET")) {
        return jsonResponse(users);
      }
      if (path === "/api/v1/admin/audit-events?limit=50&offset=0") {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      if (path === "/api/v1/admin/users/player-1" && init?.method === "DELETE") {
        return jsonResponse({ deleted: true });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <Players me={me} />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /delete/i }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("cannot be undone"));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/users/player-1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});

describe("admin player progress", () => {
  it("lets an admin advance an incomplete player to a later clue", () => {
    const game: AdminGameDetail = {
      id: "game-advance",
      title: "Advance Hunt",
      description: null,
      instructions: null,
      closing_message: null,
      status: "open",
      player_count: 1,
      clue_count: 3,
      completion_count: 0,
      created_at: "2026-07-28T12:00:00+00:00",
      updated_at: "2026-07-28T12:00:00+00:00",
      clues: [1, 2, 3].map((position) => ({
        id: `clue-${position}`,
        position,
        title: `Clue ${position}`,
        content: `Answer ${position}`,
        code: `CODE-${position}`,
        code_set: true,
        photo: null,
        video: null,
        hints: [],
      })),
      players: [
        {
          membership_id: "membership-advance",
          user: {
            id: "player-advance",
            email_address: "advance@example.com",
            full_name: "Advance Player",
            is_admin: false,
            active: true,
            password_set: true,
            created_at: "2026-07-28T12:00:00+00:00",
            last_login_at: null,
          },
          completed_count: 0,
          completed_clue_ids: [],
          completion_rank: null,
          finished_at: null,
          completions: [],
        },
      ],
    };

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ProgressEditor game={game} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /advance/i }));

    expect(screen.getByRole("heading", { name: "Advance Advance Player" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Clue 2: Clue 2" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Clue 3: Clue 3" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Clue 1: Clue 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /reason/i })).toBeRequired();
  });

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
          hints: [],
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
          hints: [],
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

describe("admin clue hints", () => {
  it("provides sortable drag handles and accessible move controls", () => {
    const clue: AdminClue = {
      id: "clue-1",
      position: 1,
      title: "Find the clock",
      content: "At the clock",
      code: "CLOCK",
      code_set: true,
      photo: null,
      video: null,
      hints: [
        {
          id: "hint-1",
          position: 1,
          text: "Look up",
          photo: null,
          video: null,
        },
        {
          id: "hint-2",
          position: 2,
          text: "Look left",
          photo: null,
          video: null,
        },
      ],
    };
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <HintsEditor clue={clue} onChanged={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("button", { name: "Drag hint 1 to reorder" }),
    ).toHaveClass("clue-drag-handle");
    expect(
      screen.getByRole("button", { name: "Drag hint 2 to reorder" }),
    ).toHaveClass("clue-drag-handle");
    expect(screen.getByRole("button", { name: "Move hint 1 up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move hint 1 down" })).toBeEnabled();
  });

  it("lets an admin choose hint media before creating the hint", async () => {
    const clue: AdminClue = {
      id: "clue-new-hint",
      position: 1,
      title: "Find the clock",
      content: "At the clock",
      code: "CLOCK",
      code_set: true,
      photo: null,
      video: null,
      hints: [],
    };
    const createdHint = {
      id: "hint-new",
      position: 1,
      text: "Look above the door.",
      photo: null,
      video: null,
    };
    const uploadedPhoto = {
      id: "media-new",
      media_type: "photo" as const,
      original_filename: "door.png",
      content_type: "image/png",
      size_bytes: 12,
      status: "ready" as const,
      url: "/api/v1/media/media-new",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input, init) => {
        const path = String(input);
        if (
          path === "/api/v1/admin/clues/clue-new-hint/hints"
          && init?.method === "POST"
        ) {
          return jsonResponse(createdHint);
        }
        if (
          path === "/api/v1/admin/hints/hint-new/media/photo"
          && init?.method === "PUT"
        ) {
          return jsonResponse(uploadedPhoto);
        }
        throw new Error(`Unexpected request: ${path}`);
      },
    );
    const onChanged = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <HintsEditor clue={clue} onChanged={onChanged} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add hint" }));
    const photo = new File(["photo bytes"], "door.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Hint photo"), {
      target: { files: [photo] },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^Hint text/ }), {
      target: { value: "Look above the door." },
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Ready to upload: door.png/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Create hint" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      text: "Look above the door.",
    });
    expect(fetchMock.mock.calls[1][1]?.body).toBe(photo);
    expect(screen.getByText("Look above the door.")).toBeInTheDocument();
  });
});

describe("admin game audit history", () => {
  it("adds a game-filtered audit tab after progress", async () => {
    const game: AdminGameDetail = {
      id: "game-audit",
      title: "Audited Hunt",
      description: null,
      instructions: null,
      closing_message: null,
      status: "open",
      player_count: 0,
      clue_count: 0,
      completion_count: 0,
      created_at: "2026-07-28T12:00:00+00:00",
      updated_at: "2026-07-28T12:00:00+00:00",
      clues: [],
      players: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input) => {
        const path = String(input);
        if (path === "/api/v1/admin/games/game-audit") {
          return jsonResponse(game);
        }
        if (path === "/api/v1/admin/users") {
          return jsonResponse([]);
        }
        if (
          path
          === "/api/v1/admin/audit-events?limit=50&offset=0&game_id=game-audit"
        ) {
          return jsonResponse({
            items: [],
            total: 0,
            limit: 50,
            offset: 0,
          });
        }
        throw new Error(`Unexpected request: ${path}`);
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <GameEditor gameId={game.id} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    const auditTab = await screen.findByRole("button", {
      name: "Audit history",
    });
    const tabs = screen.getAllByRole("navigation")[0].querySelectorAll("button");
    expect(Array.from(tabs).map((tab) => tab.textContent)).toEqual([
      "Clues",
      "Players",
      "Progress",
      "Audit history",
    ]);

    fireEvent.click(auditTab);

    expect(
      await screen.findByRole("heading", { name: "Game audit history" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/admin/audit-events?limit=50&offset=0&game_id=game-audit",
      expect.any(Object),
    );
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
        game: { id: "game-1", title: "Downtown Hunt" },
      },
    ];

    render(<AuditTable events={events} />);

    expect(screen.getByText("Player One")).toBeInTheDocument();
    expect(screen.getByText("Completed a clue")).toBeInTheDocument();
    expect(screen.getByText("Downtown Hunt")).toBeInTheDocument();
    expect(screen.getByText("Clue 2")).toBeInTheDocument();
    expect(screen.getByText("Jul 28, 2026, 10:35 AM")).toHaveAttribute(
      "datetime",
      events[0].created_at,
    );
    expect(screen.getByText("Record details")).toBeInTheDocument();
  });

  it("shows player hint reveals with the hint number", () => {
    const event: AuditEvent = {
      id: "event-hint",
      action: "hint.revealed",
      entity_type: "hint",
      entity_id: "hint-2",
      reason: null,
      before: null,
      after: {
        game_id: "game-1",
        clue_id: "clue-1",
        position: 2,
      },
      request_id: "request-hint",
      created_at: "2026-07-28T14:35:00+00:00",
      actor: {
        id: "player-1",
        email_address: "player@example.com",
        full_name: "Player One",
        is_admin: false,
      },
      subject: null,
      game: { id: "game-1", title: "Downtown Hunt" },
    };

    render(<AuditTable events={[event]} />);

    expect(screen.getByText("Player One")).toBeInTheDocument();
    expect(screen.getByText("Revealed hint")).toBeInTheDocument();
    expect(screen.getByText("Hint 2")).toBeInTheDocument();
    expect(screen.getByText("Downtown Hunt")).toBeInTheDocument();
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
        game: null,
      },
    ];

    render(<AuditTable events={events} />);

    expect(screen.getByText("Unknown account")).toBeInTheDocument();
    expect(screen.getByText("Sign-in rejected")).toBeInTheDocument();
    expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
  });
});
