import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
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

const confettiColors = ["#8cd624", "#2395d3", "#f6be00", "#6738a7", "#ef476f", "#ffffff"];

function ClueConfetti({ grandFinale = false }: { grandFinale?: boolean }) {
  const pieceCount = grandFinale ? 160 : 72;
  return (
    <div
      className={`confetti-burst ${grandFinale ? "confetti-burst--finale" : ""}`}
      aria-hidden="true"
    >
      {Array.from({ length: pieceCount }, (_, index) => {
        const style = {
          "--confetti-color": confettiColors[index % confettiColors.length],
          "--confetti-left": `${(index * 37) % 101}%`,
          "--confetti-delay": `${(index % (grandFinale ? 18 : 12)) * 24}ms`,
          "--confetti-duration": `${
            (grandFinale ? 1650 : 1050) + (index % 8) * 90
          }ms`,
          "--confetti-drift": `${((index * 29) % 35) - 17}vw`,
          "--confetti-spin": `${540 + (index % 5) * 180}deg`,
        } as React.CSSProperties;
        return <i className="confetti-burst__piece" style={style} key={index} />;
      })}
    </div>
  );
}

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
          <strong>{me.full_name}</strong>
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
            <div className="eyebrow">Welcome back, {me.full_name}</div>
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
  const [freshRevealId, setFreshRevealId] = useState<string | null>(null);
  const revealRef = useRef<HTMLElement>(null);
  const queryClient = useQueryClient();
  const game = useQuery({
    queryKey: ["player-game", gameId],
    queryFn: () => api<PlayerGameDetail>(`/api/v1/player/games/${gameId}`),
  });
  const current = game.data?.clues.find((clue) => clue.status === "current");
  const completedClues =
    game.data?.clues.filter((clue) => clue.status === "completed") ?? [];
  const latestCompleted = completedClues.at(-1);
  const earlierCompleted = completedClues.slice(0, -1);
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
      if (result.created) {
        const revealed = result.game.clues.filter(
          (clue) => clue.status === "completed",
        ).at(-1);
        setFreshRevealId(revealed?.id ?? null);
      }
    },
  });

  useEffect(() => {
    if (!freshRevealId || latestCompleted?.id !== freshRevealId) return;
    const frame = window.requestAnimationFrame(() => {
      revealRef.current?.focus({ preventScroll: true });
      revealRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [freshRevealId, latestCompleted?.id]);

  function submit(event: FormEvent) {
    event.preventDefault();
    complete.mutate();
  }

  return (
    <div className="player-shell">
      {freshRevealId && (
        <ClueConfetti key={freshRevealId} grandFinale={game.data?.complete} />
      )}
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
            {latestCompleted && (
              <section
                className={`reveal-card ${freshRevealId === latestCompleted.id ? "reveal-card--fresh" : ""}`}
                ref={revealRef}
                tabIndex={-1}
                aria-live="polite"
              >
                <header className="reveal-card__head">
                  <span><CheckCircle2 /> Answer revealed</span>
                  <small>{game.data.completed_count} of {game.data.clue_count}</small>
                </header>
                <div className="reveal-card__body">
                  <div className="eyebrow">Clue {latestCompleted.position}</div>
                  <h2>{latestCompleted.clue}</h2>
                  <div className="reveal-card__answer">
                    <div className="eyebrow">Answer</div>
                    <p>{latestCompleted.answer}</p>
                  </div>
                </div>
              </section>
            )}
            {game.data.complete ? (
              <section className="completion-card">
                <PartyPopper />
                <div className="eyebrow">Hunt complete</div>
                <h2>You found them all!</h2>
                <p>
                  {game.data.closing_message ||
                    "You unlocked every clue in this game. Nice work."}
                </p>
              </section>
            ) : current && game.data.status === "open" ? (
              <section className="unlock-card">
                <div className="unlock-card__number">Clue {current.position}</div>
                <KeyRound />
                <div className="eyebrow">Clue</div>
                <h2 className="unlock-card__clue">{current.clue}</h2>
                <p>
                  Enter this clue’s code to reveal the answer.
                </p>
                <form onSubmit={submit}>
                  <input
                    aria-label={`Code for clue ${current.position}`}
                    autoCapitalize="characters"
                    autoComplete="off"
                    placeholder="ENTER CODE"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    required
                  />
                  <Button busy={complete.isPending} type="submit">Reveal answer</Button>
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
                <div><h2>This game is closed</h2><p>Your most recently unlocked clue remains above.</p></div>
              </section>
            )}
            {earlierCompleted.length > 0 && (
              <section className="clue-timeline">
                <div className="section-title">
                  <div className="eyebrow">Your trail</div>
                  <h2>Earlier clues</h2>
                </div>
                {earlierCompleted.map((clue) => (
                  <article className="clue-row clue-row--completed" key={clue.position}>
                  <div className="clue-row__marker">
                    <Check />
                  </div>
                  <div>
                    <span className="clue-row__label">Clue {clue.position}</span>
                    <h3>{clue.clue}</h3>
                    <strong className="clue-row__answer-label">Answer</strong>
                    <p>{clue.answer}</p>
                    <small><CheckCircle2 /> Unlocked</small>
                  </div>
                </article>
                ))}
              </section>
            )}
            {!game.data.clue_count && (
              <EmptyState icon={<Flag />} title="No clues configured">
                This game does not have any clues yet.
              </EmptyState>
            )}
          </>
        )}
      </main>
    </div>
  );
}
