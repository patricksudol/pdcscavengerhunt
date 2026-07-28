import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Flag,
  KeyRound,
  LockKeyhole,
  LogOut,
  Map,
  PartyPopper,
  ShieldCheck,
} from "lucide-react";

import {
  api,
  Me,
  PlayerGame,
  PlayerGameDetail,
  postJson,
  setCsrfToken,
} from "./api";
import { Brand, Button, EmptyState, ErrorMessage, StatusBadge } from "./components";

export function PlayerPage({ me }: { me: Me }) {
  const gameMatch = window.location.pathname.match(/^\/games\/([^/]+)/);
  const gameId = gameMatch ? decodeURIComponent(gameMatch[1]) : null;
  return gameId ? <GameView me={me} gameId={gameId} /> : <GameList me={me} />;
}

function PlayerHeader({ me }: { me: Me }) {
  const logout = useMutation({
    mutationFn: () => api("/api/v1/auth/logout", { method: "POST" }),
    onSuccess: () => {
      setCsrfToken(null);
      window.location.assign("/");
    },
  });
  return (
    <header className="player-header">
      <Brand compact />
      <div className="player-header__actions">
        <span className="player-identity">
          <small>Playing as</small>
          <strong>{me.display_name}</strong>
        </span>
        {me.is_admin && <a className="button button--quiet button--small" href="/admin">Admin</a>}
        <button
          className="icon-button"
          aria-label="Sign out"
          title="Sign out"
          onClick={() => logout.mutate()}
        >
          <LogOut />
        </button>
      </div>
    </header>
  );
}

function GameList({ me }: { me: Me }) {
  const games = useQuery({
    queryKey: ["player-games"],
    queryFn: () => api<PlayerGame[]>("/api/v1/player/games"),
  });
  return (
    <div className="player-shell">
      <PlayerHeader me={me} />
      <main className="player-main">
        <header className="hero">
          <div>
            <div className="eyebrow">Welcome back, {me.display_name}</div>
            <h1>Choose your adventure</h1>
            <p>Your assigned hunts and progress are collected here.</p>
          </div>
          <Map aria-hidden="true" />
        </header>
        {games.isLoading ? (
          <div className="game-grid"><div className="game-card skeleton" /><div className="game-card skeleton" /></div>
        ) : games.isError ? (
          <ErrorMessage error={games.error} />
        ) : !games.data?.length ? (
          <EmptyState icon={<Map />} title="No games yet">
            An administrator has not assigned you to an open game.
          </EmptyState>
        ) : (
          <section className="game-grid" aria-label="Your games">
            {games.data.map((game) => {
              const percent = game.clue_count
                ? Math.round((game.completed_count / game.clue_count) * 100)
                : 0;
              return (
                <a className="game-card" href={`/games/${game.id}`} key={game.id}>
                  <div className="game-card__top">
                    <StatusBadge status={game.status} />
                    <ChevronRight />
                  </div>
                  <div className="game-card__icon"><Map /></div>
                  <h2>{game.title}</h2>
                  <p>{game.description || "A new scavenger hunt awaits."}</p>
                  <div className="progress">
                    <div><span style={{ width: `${percent}%` }} /></div>
                    <small>{game.completed_count} of {game.clue_count} clues</small>
                  </div>
                </a>
              );
            })}
          </section>
        )}
      </main>
    </div>
  );
}

function GameView({ me, gameId }: { me: Me; gameId: string }) {
  const [code, setCode] = useState("");
  const queryClient = useQueryClient();
  const game = useQuery({
    queryKey: ["player-game", gameId],
    queryFn: () => api<PlayerGameDetail>(`/api/v1/player/games/${gameId}`),
  });
  const current = game.data?.clues.find((clue) => clue.status === "current");
  const complete = useMutation({
    mutationFn: () =>
      postJson<{ created: boolean; game: PlayerGameDetail }>(
        `/api/v1/player/games/${gameId}/clues/${current?.id}/complete`,
        { code },
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(["player-game", gameId], result.game);
      queryClient.invalidateQueries({ queryKey: ["player-games"] });
      setCode("");
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    complete.mutate();
  }

  return (
    <div className="player-shell">
      <PlayerHeader me={me} />
      <main className="hunt-main">
        <a className="back-link" href="/"><ArrowLeft /> All games</a>
        {game.isLoading ? (
          <div className="hunt-card skeleton" />
        ) : game.isError || !game.data ? (
          <ErrorMessage error={game.error} />
        ) : (
          <>
            <header className="hunt-title">
              <div>
                <StatusBadge status={game.data.status} />
                <h1>{game.data.title}</h1>
                <p>{game.data.description}</p>
              </div>
              <div className="hunt-score">
                <strong>{game.data.completed_count}</strong>
                <span>of {game.data.clue_count}<br />unlocked</span>
              </div>
            </header>
            {game.data.instructions && (
              <aside className="instructions"><ShieldCheck /> <span>{game.data.instructions}</span></aside>
            )}
            {game.data.complete ? (
              <section className="completion-card">
                <PartyPopper />
                <div className="eyebrow">Hunt complete</div>
                <h2>You found them all!</h2>
                <p>Every clue in this game has been unlocked. Nice work.</p>
              </section>
            ) : current && game.data.status === "open" ? (
              <section className="unlock-card">
                <div className="unlock-card__number">Clue {current.position}</div>
                <KeyRound />
                <h2>Enter the code you found</h2>
                <p>The correct code reveals this clue and opens the next stop.</p>
                <form onSubmit={submit}>
                  <input
                    aria-label="Clue code"
                    autoCapitalize="characters"
                    autoComplete="off"
                    placeholder="ENTER CODE"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    required
                  />
                  <Button busy={complete.isPending} type="submit">Unlock clue</Button>
                </form>
                <ErrorMessage error={complete.error} />
              </section>
            ) : game.data.status === "open" && game.data.clue_count === 0 ? (
              <section className="closed-notice">
                <Flag />
                <div><h2>Clues are being prepared</h2><p>Check back soon for the first stop.</p></div>
              </section>
            ) : (
              <section className="closed-notice">
                <LockKeyhole />
                <div><h2>This game is closed</h2><p>Your unlocked clues remain below.</p></div>
              </section>
            )}
            <section className="clue-timeline">
              <div className="section-title">
                <div className="eyebrow">Your trail</div>
                <h2>Clue progress</h2>
              </div>
              {game.data.clues.map((clue) => (
                <article className={`clue-row clue-row--${clue.status}`} key={clue.position}>
                  <div className="clue-row__marker">
                    {clue.status === "completed" ? <Check /> : clue.status === "current" ? <CircleDot /> : <LockKeyhole />}
                  </div>
                  <div>
                    <span className="clue-row__label">Clue {clue.position}</span>
                    {clue.status === "completed" ? (
                      <>
                        <h3>{clue.title}</h3>
                        <p>{clue.content}</p>
                        <small><CheckCircle2 /> Unlocked</small>
                      </>
                    ) : clue.status === "current" ? (
                      <><h3>Code required</h3><p>Find and enter the code for this stop.</p></>
                    ) : (
                      <><h3>Locked</h3><p>Complete the earlier clues first.</p></>
                    )}
                  </div>
                </article>
              ))}
              {!game.data.clue_count && (
                <EmptyState icon={<Flag />} title="No clues configured">
                  This game does not have any clues yet.
                </EmptyState>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
