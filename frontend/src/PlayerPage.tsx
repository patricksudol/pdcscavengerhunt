import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  Flag,
  KeyRound,
  LogOut,
  Map,
  MapPin,
  PartyPopper,
  ShieldCheck,
  Trophy,
} from "lucide-react";

import {
  api,
  ClueMedia,
  Me,
  PlayerClue,
  PlayerGame,
  PlayerGameDetail,
  postJson,
  setCsrfToken,
} from "./api";
import { Brand, Button, EmptyState, ErrorMessage, StatusBadge } from "./components";

const confettiColors = ["#8cd624", "#2395d3", "#f6be00", "#6738a7", "#ef476f", "#ffffff"];

export function ClueMediaAttachments({
  photo,
  video,
  clueTitle,
}: {
  photo?: ClueMedia | null;
  video?: ClueMedia | null;
  clueTitle?: string;
}) {
  if (!photo && !video) return null;
  return (
    <div className="clue-media">
      {photo && (
        <img
          src={photo.url}
          alt={clueTitle ? `Photo for ${clueTitle}` : "Clue photo"}
          loading="lazy"
        />
      )}
      {video && (
        <iframe
          src={video.url}
          title={clueTitle ? `Video for ${clueTitle}` : "Clue video"}
          aria-label={clueTitle ? `Video for ${clueTitle}` : "Clue video"}
          allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
          allowFullScreen
        />
      )}
    </div>
  );
}

export function ClueDetailCard({
  clue,
  clueCount,
  gameStatus,
  code,
  busy,
  error,
  onCodeChange,
  onSubmit,
}: {
  clue: PlayerClue;
  clueCount: number;
  gameStatus: PlayerGameDetail["status"];
  code: string;
  busy: boolean;
  error: unknown;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const headingId = `clue-${clue.position}`;
  const completed = clue.status === "completed";
  return (
    <section className="unlock-card" aria-labelledby={headingId}>
      <header className="unlock-card__head">
        <span>
          {completed
            ? <CheckCircle2 aria-hidden="true" />
            : <MapPin aria-hidden="true" />}
          {completed ? "Clue solved" : "Your selected clue"}
        </span>
        <small>Clue {clue.position} of {clueCount}</small>
      </header>
      <div className="unlock-card__body">
        <span className="unlock-card__icon" aria-hidden="true">
          {completed ? <Check /> : <KeyRound />}
        </span>
        <div className="eyebrow">{completed ? "Nice work" : "Your challenge"}</div>
        <h1 className="unlock-card__clue" id={headingId}>{clue.clue}</h1>
        <ClueMediaAttachments
          photo={clue.photo}
          video={clue.video}
          clueTitle={clue.clue}
        />
        {completed ? (
          <div className="unlock-card__answer">
            <div className="eyebrow">Answer</div>
            <p>{clue.answer}</p>
          </div>
        ) : gameStatus === "open" ? (
          <>
            <p>Solve this clue, then enter the code you find to reveal the answer.</p>
            <form onSubmit={onSubmit}>
              <input
                aria-label={`Code for clue ${clue.position}`}
                autoCapitalize="characters"
                autoComplete="off"
                placeholder="ENTER CODE"
                value={code}
                onChange={(event) => onCodeChange(event.target.value)}
                required
              />
              <Button busy={busy} type="submit">Solve clue</Button>
            </form>
            <ErrorMessage error={error} />
          </>
        ) : (
          <p>This game is closed, so this clue can no longer be solved.</p>
        )}
      </div>
    </section>
  );
}

export function ClueList({
  gameId,
  clues,
}: {
  gameId: string;
  clues: PlayerClue[];
}) {
  return (
    <section className="clue-picker" aria-labelledby="clue-picker-title">
      <header className="section-title">
        <div className="eyebrow">Choose a clue</div>
        <h2 id="clue-picker-title">Pick your next challenge</h2>
        <p>Select any clue to see the full challenge and enter its code.</p>
      </header>
      <div className="clue-picker__list">
        {clues.map((clue) => {
          const completed = clue.status === "completed";
          return (
            <a
              className={`clue-choice ${completed ? "clue-choice--completed" : ""}`}
              href={`/games/${encodeURIComponent(gameId)}/clues/${encodeURIComponent(clue.id)}`}
              key={clue.id}
            >
              <span className="clue-choice__number">{clue.position}</span>
              <span className="clue-choice__copy">
                <small>Clue {clue.position}</small>
                <strong>{clue.clue}</strong>
              </span>
              <span className="clue-choice__status">
                {completed ? <><CheckCircle2 /> Solved</> : <>View clue <ChevronRight /></>}
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}

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
  const gameMatch = window.location.pathname.match(
    /^\/games\/([^/]+)(?:\/clues\/([^/]+))?/,
  );
  const gameId = gameMatch ? decodeURIComponent(gameMatch[1]) : null;
  const clueId = gameMatch?.[2] ? decodeURIComponent(gameMatch[2]) : null;
  return gameId
    ? <GameView me={me} gameId={gameId} clueId={clueId} />
    : <GameList me={me} />;
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
                    {game.clue_count > 0 &&
                    game.completed_count === game.clue_count ? (
                      <span className="game-card__complete">
                        <CheckCircle2 /> Completed
                      </span>
                    ) : (
                      <StatusBadge status={game.status} />
                    )}
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

function GameView({
  me,
  gameId,
  clueId,
}: {
  me: Me;
  gameId: string;
  clueId: string | null;
}) {
  const [code, setCode] = useState("");
  const [celebration, setCelebration] = useState<{
    clueId: string;
    grandFinale: boolean;
  } | null>(null);
  const redirectTimerRef = useRef<number | null>(null);
  const queryClient = useQueryClient();
  const game = useQuery({
    queryKey: ["player-game", gameId],
    queryFn: () => api<PlayerGameDetail>(`/api/v1/player/games/${gameId}`),
  });
  const selectedClue = clueId
    ? game.data?.clues.find((clue) => clue.id === clueId)
    : null;
  const complete = useMutation({
    mutationFn: () =>
      postJson<{ created: boolean; game: PlayerGameDetail }>(
        `/api/v1/player/games/${gameId}/clues/${selectedClue?.id}/complete`,
        { code },
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(["player-game", gameId], result.game);
      queryClient.invalidateQueries({ queryKey: ["player-games"] });
      setCode("");
      if (result.created) {
        setCelebration({
          clueId: selectedClue?.id ?? "",
          grandFinale: result.game.complete,
        });
        redirectTimerRef.current = window.setTimeout(
          () => window.location.assign(`/games/${encodeURIComponent(gameId)}`),
          result.game.complete ? 2600 : 1500,
        );
      }
    },
  });

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current !== null) {
        window.clearTimeout(redirectTimerRef.current);
      }
    };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    complete.mutate();
  }

  return (
    <div className="player-shell">
      {celebration && (
        <>
          <ClueConfetti
            key={celebration.clueId}
            grandFinale={celebration.grandFinale}
          />
          <div className={`solve-celebration ${celebration.grandFinale ? "solve-celebration--finale" : ""}`} role="status">
            {celebration.grandFinale ? <Trophy /> : <CheckCircle2 />}
            <strong>{celebration.grandFinale ? "You did it!" : "Clue solved!"}</strong>
            <span>
              {celebration.grandFinale
                ? "You completed every clue."
                : "Returning to the clue list…"}
            </span>
          </div>
        </>
      )}
      <PlayerHeader me={me} />
      <main className="hunt-main">
        <a
          className="back-link"
          href={clueId ? `/games/${encodeURIComponent(gameId)}` : "/"}
        >
          <ArrowLeft /> {clueId ? "Back to clue list" : "All games"}
        </a>
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
                <span>of {game.data.clue_count}<br />solved</span>
              </div>
            </header>
            {game.data.instructions && (
              <aside className="instructions"><ShieldCheck /> <span>{game.data.instructions}</span></aside>
            )}
            {!clueId && game.data.complete && (
              <section className="completion-banner" role="status">
                <PartyPopper aria-hidden="true" />
                <div>
                  <div className="eyebrow">Game complete</div>
                  <h2>You did it!</h2>
                  <p>
                    {game.data.closing_message ||
                      "You solved every clue in this game. Nice work."}
                  </p>
                </div>
                <Trophy aria-hidden="true" />
              </section>
            )}
            {clueId && selectedClue ? (
              <ClueDetailCard
                clue={selectedClue}
                clueCount={game.data.clue_count}
                gameStatus={game.data.status}
                code={code}
                busy={complete.isPending || Boolean(celebration)}
                error={complete.error}
                onCodeChange={setCode}
                onSubmit={submit}
              />
            ) : clueId ? (
              <EmptyState icon={<Flag />} title="Clue not found">
                This clue is not part of this game. Return to the clue list and
                choose another one.
              </EmptyState>
            ) : game.data.clue_count ? (
              <ClueList gameId={gameId} clues={game.data.clues} />
            ) : (
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
