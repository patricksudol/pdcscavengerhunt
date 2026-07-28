import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Check,
  ChevronDown,
  ChevronUp,
  Clipboard,
  Gamepad2,
  KeyRound,
  ListChecks,
  LockKeyhole,
  LogOut,
  Menu,
  Pencil,
  Plus,
  Shield,
  Trash2,
  UserCog,
  Users,
  X,
} from "lucide-react";

import {
  AdminClue,
  AdminGame,
  AdminGameDetail,
  AdminUser,
  api,
  Me,
  postJson,
  setCsrfToken,
} from "./api";
import {
  Brand,
  Button,
  EmptyState,
  ErrorMessage,
  Field,
  Modal,
  StatusBadge,
  TextArea,
} from "./components";

export function AdminPage({ me }: { me: Me }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const path = window.location.pathname.replace(/\/+$/, "") || "/admin";
  const logout = useMutation({
    mutationFn: () => api("/api/v1/auth/logout", { method: "POST" }),
    onSuccess: () => {
      setCsrfToken(null);
      window.location.assign("/");
    },
  });
  const page =
    path === "/admin/players" ? <Players /> :
    path === "/admin/games" ? <Games /> :
    path === "/admin/security" ? <Security /> :
    <Overview />;
  return (
    <div className="admin-shell">
      {menuOpen && <button className="sidebar-scrim" onClick={() => setMenuOpen(false)} aria-label="Close menu" />}
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__head">
          <Brand compact />
          <button className="icon-button sidebar__close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X /></button>
        </div>
        <nav onClick={() => setMenuOpen(false)}>
          <a href="/admin" className={path === "/admin" ? "active" : ""}><BarChart3 /> Overview</a>
          <a href="/admin/games" className={path === "/admin/games" ? "active" : ""}><Gamepad2 /> Games</a>
          <a href="/admin/players" className={path === "/admin/players" ? "active" : ""}><Users /> Players</a>
          <a href="/admin/security" className={path === "/admin/security" ? "active" : ""}><KeyRound /> My password</a>
          <a href="/"><ListChecks /> Player view</a>
        </nav>
        <div className="sidebar__user">
          <div>{initials(me.display_name)}</div>
          <span><strong>{me.display_name}</strong><small>Administrator</small></span>
          <button className="icon-button" onClick={() => logout.mutate()} aria-label="Sign out"><LogOut /></button>
        </div>
      </aside>
      <div className="admin-main">
        <header className="admin-topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu /></button>
          <div><span>Administration</span><strong>PDC Scavenger Hunt</strong></div>
          <span className="admin-topbar__user">{me.username}</span>
        </header>
        <main className="admin-content">{page}</main>
      </div>
    </div>
  );
}

function initials(value: string) {
  return value.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function PageTitle({ eyebrow, title, children }: { eyebrow: string; title: string; children?: React.ReactNode }) {
  return (
    <header className="page-title title-action">
      <div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1></div>
      {children}
    </header>
  );
}

function Overview() {
  const data = useQuery({
    queryKey: ["admin-dashboard"],
    queryFn: () => api<{ users: number; games: number; open_games: number; completions: number }>("/api/v1/admin/dashboard"),
  });
  return (
    <>
      <PageTitle eyebrow="Control center" title="Hunt overview" />
      <section className="stat-grid">
        <Stat icon={<Users />} value={data.data?.users ?? "—"} label="Active players" color="blue" />
        <Stat icon={<Gamepad2 />} value={data.data?.games ?? "—"} label="Total games" color="purple" />
        <Stat icon={<ListChecks />} value={data.data?.completions ?? "—"} label="Clues unlocked" color="lime" />
        <Stat icon={<Shield />} value={data.data?.open_games ?? "—"} label="Open games" color="gold" />
      </section>
      <section className="welcome-panel">
        <div>
          <div className="eyebrow">Ready to build a trail?</div>
          <h2>Set up the next adventure</h2>
          <p>Create a game, add its clues in order, then invite and assign your players.</p>
        </div>
        <a className="button button--primary" href="/admin/games">Manage games</a>
      </section>
    </>
  );
}

function Stat({ icon, value, label, color }: { icon: React.ReactNode; value: number | string; label: string; color: string }) {
  return <div className={`stat stat--${color}`}><span className="stat__icon">{icon}</span><span><strong>{value}</strong><small>{label}</small></span></div>;
}

function Players() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [setupUrl, setSetupUrl] = useState<string | null>(null);
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<AdminUser[]>("/api/v1/admin/users"),
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<AdminUser> }) =>
      postJson<AdminUser>(`/api/v1/admin/users/${id}`, changes, "PATCH"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  const invite = useMutation({
    mutationFn: (id: string) => postJson<{ setup_url: string }>(`/api/v1/admin/users/${id}/setup-link`, {}),
    onSuccess: (result) => setSetupUrl(result.setup_url),
  });
  return (
    <>
      <PageTitle eyebrow="People & access" title="Players">
        <Button onClick={() => setCreating(true)}><Plus /> Add player</Button>
      </PageTitle>
      <p className="page-lede">Provision player accounts, manage administrator access, and issue password invitations.</p>
      <section className="panel">
        <ErrorMessage error={update.error || invite.error} />
        {users.isLoading ? <div className="panel-loading">Loading players…</div> :
          users.isError ? <ErrorMessage error={users.error} /> :
          !users.data?.length ? <EmptyState icon={<Users />} title="No players">Create the first player to begin.</EmptyState> :
          <div className="table">
            <div className="user-table user-table--head"><span>Player</span><span>Games</span><span>Access</span><span>Status</span><span>Actions</span></div>
            {users.data.map((user) => (
              <div className="user-table" key={user.id}>
                <span className="person-cell"><span className="avatar">{initials(user.display_name)}</span><span><strong>{user.display_name}</strong><small>@{user.username}</small></span></span>
                <span>{user.game_count ?? 0}</span>
                <span>
                  <label className="switch-label">
                    <input type="checkbox" checked={user.is_admin} onChange={(event) => update.mutate({ id: user.id, changes: { is_admin: event.target.checked } })} />
                    Admin
                  </label>
                </span>
                <span><StatusBadge status={user.active ? "active" : "inactive"} /></span>
                <span className="row-actions">
                  <Button variant="quiet" onClick={() => setEditing(user)}>Edit</Button>
                  <Button variant="secondary" onClick={() => invite.mutate(user.id)}>{user.password_set ? "New link" : "Invite"}</Button>
                  <Button variant="quiet" onClick={() => update.mutate({ id: user.id, changes: { active: !user.active } })}>{user.active ? "Deactivate" : "Activate"}</Button>
                </span>
              </div>
            ))}
          </div>
        }
      </section>
      {creating && <CreatePlayer onClose={() => setCreating(false)} onCreated={(url) => { setCreating(false); setSetupUrl(url); queryClient.invalidateQueries({ queryKey: ["admin-users"] }); }} />}
      {editing && <EditPlayer user={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); queryClient.invalidateQueries({ queryKey: ["admin-users"] }); }} />}
      {setupUrl && <InviteModal url={setupUrl} onClose={() => setSetupUrl(null)} />}
    </>
  );
}

function EditPlayer({ user, onClose, onSaved }: { user: AdminUser; onClose: () => void; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [active, setActive] = useState(user.active);
  const save = useMutation({
    mutationFn: () => postJson<AdminUser>(`/api/v1/admin/users/${user.id}`, { display_name: displayName, is_admin: isAdmin, active }, "PATCH"),
    onSuccess: onSaved,
  });
  return (
    <Modal title="Edit player" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <Field label="Display name" name="edit-display-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
        <Field label="Username" name="edit-username" value={user.username} disabled />
        <label className="check-field"><input type="checkbox" checked={isAdmin} onChange={(event) => setIsAdmin(event.target.checked)} /><span><strong>Administrator</strong><small>Can configure games, clues, and players.</small></span></label>
        <label className="check-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span><strong>Active account</strong><small>Inactive users cannot sign in or play.</small></span></label>
        <ErrorMessage error={save.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={save.isPending} type="submit">Save player</Button></div>
      </form>
    </Modal>
  );
}

function CreatePlayer({ onClose, onCreated }: { onClose: () => void; onCreated: (url: string) => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const create = useMutation({
    mutationFn: () => postJson<AdminUser & { setup_url: string }>("/api/v1/admin/users", { username, display_name: displayName, is_admin: isAdmin }),
    onSuccess: (result) => onCreated(result.setup_url),
  });
  return (
    <Modal title="Add player" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="Display name" name="display-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
        <Field label="Username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} hint="Letters, numbers, periods, underscores, and hyphens." required minLength={3} />
        <label className="check-field"><input type="checkbox" checked={isAdmin} onChange={(event) => setIsAdmin(event.target.checked)} /><span><strong>Administrator</strong><small>Can configure all games, clues, and players.</small></span></label>
        <ErrorMessage error={create.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={create.isPending} type="submit">Create & invite</Button></div>
      </form>
    </Modal>
  );
}

function InviteModal({ url, onClose }: { url: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
  }
  return (
    <Modal title="Password invitation" onClose={onClose}>
      <div className="modal-form">
        <p>Send this single-use link through a trusted channel. It expires in 24 hours.</p>
        <div className="copy-box"><code>{url}</code><Button variant="secondary" onClick={copy}>{copied ? <Check /> : <Clipboard />}{copied ? "Copied" : "Copy"}</Button></div>
        <div className="modal-actions"><Button onClick={onClose}>Done</Button></div>
      </div>
    </Modal>
  );
}

function Games() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const games = useQuery({
    queryKey: ["admin-games"],
    queryFn: () => api<AdminGame[]>("/api/v1/admin/games"),
  });
  return (
    <>
      <PageTitle eyebrow="Game builder" title="Games">
        <Button onClick={() => setCreating(true)}><Plus /> New game</Button>
      </PageTitle>
      <p className="page-lede">Create a hunt, arrange its clues, assign players, and open it when ready.</p>
      {games.isLoading ? <div className="panel-loading">Loading games…</div> :
        games.isError ? <ErrorMessage error={games.error} /> :
        !games.data?.length ? <EmptyState icon={<Gamepad2 />} title="No games yet">Create your first scavenger hunt.</EmptyState> :
        <section className="admin-game-grid">
          {games.data.map((game) => (
            <button className="admin-game-card" key={game.id} onClick={() => setSelected(game.id)}>
              <div><StatusBadge status={game.status} /><span>{game.clue_count} clues</span></div>
              <h2>{game.title}</h2>
              <p>{game.description || "No description"}</p>
              <footer><span><Users /> {game.player_count}</span><span><ListChecks /> {game.completion_count}</span><strong>Edit game →</strong></footer>
            </button>
          ))}
        </section>
      }
      {creating && <CreateGame onClose={() => setCreating(false)} onCreated={(game) => { setCreating(false); setSelected(game.id); queryClient.invalidateQueries({ queryKey: ["admin-games"] }); }} />}
      {selected && <GameEditor gameId={selected} onClose={() => { setSelected(null); queryClient.invalidateQueries({ queryKey: ["admin-games"] }); }} />}
    </>
  );
}

function CreateGame({ onClose, onCreated }: { onClose: () => void; onCreated: (game: AdminGame) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const create = useMutation({
    mutationFn: () => postJson<AdminGame>("/api/v1/admin/games", { title, description: description || null, instructions: instructions || null }),
    onSuccess: onCreated,
  });
  return (
    <Modal title="Create game" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="Game title" name="title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Description" name="description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        <TextArea label="Player instructions" name="instructions" rows={3} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        <ErrorMessage error={create.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={create.isPending} type="submit">Create game</Button></div>
      </form>
    </Modal>
  );
}

function GameEditor({ gameId, onClose }: { gameId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"clues" | "players" | "progress">("clues");
  const [editingClue, setEditingClue] = useState<AdminClue | "new" | null>(null);
  const [editingGame, setEditingGame] = useState(false);
  const detail = useQuery({
    queryKey: ["admin-game", gameId],
    queryFn: () => api<AdminGameDetail>(`/api/v1/admin/games/${gameId}`),
  });
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<AdminUser[]>("/api/v1/admin/users"),
  });
  const updateGame = useMutation({
    mutationFn: (changes: Partial<AdminGame>) => postJson<AdminGame>(`/api/v1/admin/games/${gameId}`, changes, "PATCH"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] });
      queryClient.invalidateQueries({ queryKey: ["admin-games"] });
    },
  });
  const reorder = useMutation({
    mutationFn: (clueIds: string[]) => postJson(`/api/v1/admin/games/${gameId}/clues/reorder`, { clue_ids: clueIds }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/admin/clues/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }),
  });
  function move(index: number, direction: -1 | 1) {
    if (!detail.data) return;
    const ids = detail.data.clues.map((clue) => clue.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    reorder.mutate(ids);
  }
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <section className="drawer drawer--wide" onMouseDown={(event) => event.stopPropagation()}>
        <header className="drawer__head">
          <div>{detail.data && <StatusBadge status={detail.data.status} />}<h2>{detail.data?.title || "Loading game…"}</h2><p>{detail.data?.description}</p></div>
          <button className="icon-button" onClick={onClose} aria-label="Close"><X /></button>
        </header>
        {detail.data && (
          <div className="drawer__toolbar">
            <label>Status
              <select value={detail.data.status} onChange={(event) => updateGame.mutate({ status: event.target.value as AdminGame["status"] })}>
                <option value="draft">Draft</option><option value="open">Open</option><option value="closed">Closed</option>
              </select>
            </label>
            <span>{detail.data.clue_count} clues · {detail.data.player_count} players</span>
            <Button variant="quiet" onClick={() => setEditingGame(true)}><Pencil /> Edit details</Button>
          </div>
        )}
        <nav className="tabs">
          <button className={tab === "clues" ? "active" : ""} onClick={() => setTab("clues")}>Clues</button>
          <button className={tab === "players" ? "active" : ""} onClick={() => setTab("players")}>Players</button>
          <button className={tab === "progress" ? "active" : ""} onClick={() => setTab("progress")}>Progress</button>
        </nav>
        {detail.isLoading ? <div className="panel-loading">Loading game…</div> :
          detail.isError || !detail.data ? <ErrorMessage error={detail.error} /> :
          tab === "clues" ? (
            <div className="drawer-section">
              <div className="drawer-section__title"><div><h3>Clue order</h3><p>Players must unlock these from top to bottom.</p></div><Button onClick={() => setEditingClue("new")}><Plus /> Add clue</Button></div>
              {!detail.data.clues.length ? <EmptyState icon={<LockKeyhole />} title="No clues">Add the first clue and its unique code.</EmptyState> :
                <div className="clue-admin-list">{detail.data.clues.map((clue, index) => (
                  <article className="clue-admin-row" key={clue.id}>
                    <span className="clue-position">{clue.position}</span>
                    <span><strong>{clue.title}</strong><small>{clue.content}</small></span>
                    <span className="clue-admin-actions">
                      <button className="icon-button" disabled={index === 0 || reorder.isPending} onClick={() => move(index, -1)} aria-label="Move up"><ChevronUp /></button>
                      <button className="icon-button" disabled={index === detail.data!.clues.length - 1 || reorder.isPending} onClick={() => move(index, 1)} aria-label="Move down"><ChevronDown /></button>
                      <button className="icon-button" onClick={() => setEditingClue(clue)} aria-label="Edit clue"><Pencil /></button>
                      <button className="icon-button danger-icon" onClick={() => { if (window.confirm(`Delete clue ${clue.position}? Player completions for it will also be removed.`)) remove.mutate(clue.id); }} aria-label="Delete clue"><Trash2 /></button>
                    </span>
                  </article>
                ))}</div>
              }
            </div>
          ) : tab === "players" ? (
            <MembershipEditor game={detail.data} users={users.data ?? []} />
          ) : (
            <ProgressEditor game={detail.data} />
          )
        }
        {editingClue && <ClueEditor gameId={gameId} clue={editingClue === "new" ? null : editingClue} onClose={() => setEditingClue(null)} onSaved={() => { setEditingClue(null); queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }); }} />}
        {editingGame && detail.data && <GameDetailsEditor game={detail.data} onClose={() => setEditingGame(false)} onSaved={() => { setEditingGame(false); queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }); queryClient.invalidateQueries({ queryKey: ["admin-games"] }); }} />}
      </section>
    </div>
  );
}

function ProgressEditor({ game }: { game: AdminGameDetail }) {
  const queryClient = useQueryClient();
  const reset = useMutation({
    mutationFn: ({ membershipId, reason }: { membershipId: string; reason: string }) =>
      postJson(`/api/v1/admin/game-players/${membershipId}/progress`, { reason }, "DELETE"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-game", game.id] }),
  });
  function resetPlayer(membershipId: string, name: string) {
    const reason = window.prompt(`Why are you resetting ${name}'s progress?`);
    if (reason?.trim()) reset.mutate({ membershipId, reason: reason.trim() });
  }
  return (
    <div className="drawer-section">
      <div className="drawer-section__title"><div><h3>Player progress</h3><p>Live completion totals for this game.</p></div></div>
      <ErrorMessage error={reset.error} />
      {!game.players.length ? <EmptyState icon={<Users />} title="No assigned players">Assign players to begin tracking progress.</EmptyState> :
        <div className="progress-list">{game.players.map((entry) => (
          <div key={entry.user.id}>
            <span className="avatar">{initials(entry.user.display_name)}</span>
            <span><strong>{entry.user.display_name}</strong><small>@{entry.user.username}</small></span>
            <div className="mini-progress"><div><span style={{ width: `${game.clue_count ? (entry.completed_count / game.clue_count) * 100 : 0}%` }} /></div><small>{entry.completed_count} / {game.clue_count}</small></div>
            {entry.completed_count > 0 && <Button variant="quiet" busy={reset.isPending} onClick={() => resetPlayer(entry.membership_id, entry.user.display_name)}>Reset</Button>}
          </div>
        ))}</div>
      }
    </div>
  );
}

function GameDetailsEditor({ game, onClose, onSaved }: { game: AdminGameDetail; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(game.title);
  const [description, setDescription] = useState(game.description ?? "");
  const [instructions, setInstructions] = useState(game.instructions ?? "");
  const save = useMutation({
    mutationFn: () => postJson(`/api/v1/admin/games/${game.id}`, { title, description: description || null, instructions: instructions || null }, "PATCH"),
    onSuccess: onSaved,
  });
  return (
    <Modal title="Edit game details" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <Field label="Game title" name="edit-game-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Description" name="edit-game-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        <TextArea label="Player instructions" name="edit-game-instructions" rows={3} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        <ErrorMessage error={save.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={save.isPending} type="submit">Save details</Button></div>
      </form>
    </Modal>
  );
}

function MembershipEditor({ game, users }: { game: AdminGameDetail; users: AdminUser[] }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(() => new Set(game.players.map((entry) => entry.user.id)));
  useEffect(() => setSelected(new Set(game.players.map((entry) => entry.user.id))), [game.players]);
  const save = useMutation({
    mutationFn: () => postJson(`/api/v1/admin/games/${game.id}/players`, { user_ids: Array.from(selected) }, "PUT"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-game", game.id] }),
  });
  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  return (
    <div className="drawer-section">
      <div className="drawer-section__title"><div><h3>Assigned players</h3><p>Only selected active players can access this game.</p></div><Button busy={save.isPending} onClick={() => save.mutate()}>Save assignments</Button></div>
      <ErrorMessage error={save.error} />
      <div className="membership-list">{users.filter((user) => user.active).map((user) => (
        <label key={user.id}><input type="checkbox" checked={selected.has(user.id)} onChange={() => toggle(user.id)} /><span className="avatar">{initials(user.display_name)}</span><span><strong>{user.display_name}</strong><small>@{user.username}{user.is_admin ? " · Admin" : ""}</small></span></label>
      ))}</div>
    </div>
  );
}

function ClueEditor({ gameId, clue, onClose, onSaved }: { gameId: string; clue: AdminClue | null; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(clue?.title ?? "");
  const [content, setContent] = useState(clue?.content ?? "");
  const [code, setCode] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const payload: { title: string; content: string; code?: string } = { title, content };
      if (code) payload.code = code;
      return clue
        ? postJson(`/api/v1/admin/clues/${clue.id}`, payload, "PATCH")
        : postJson(`/api/v1/admin/games/${gameId}/clues`, { ...payload, code });
    },
    onSuccess: onSaved,
  });
  return (
    <Modal title={clue ? `Edit clue ${clue.position}` : "Add clue"} onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <Field label="Clue title" name="clue-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Revealed content" name="content" rows={5} value={content} onChange={(event) => setContent(event.target.value)} required />
        <Field label={clue ? "Replacement code (optional)" : "Unique code"} name="code" autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} required={!clue} hint={clue ? "Leave blank to keep the existing code." : "Codes are case-insensitive and cannot be reused."} />
        <ErrorMessage error={save.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={save.isPending} type="submit">Save clue</Button></div>
      </form>
    </Modal>
  );
}

function Security() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const change = useMutation({
    mutationFn: () => postJson("/api/v1/auth/password", { current_password: currentPassword, password }),
    onSuccess: () => { setCsrfToken(null); window.location.assign("/"); },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (password === confirmation) change.mutate();
  }
  return (
    <>
      <PageTitle eyebrow="Account security" title="My password" />
      <section className="panel security-panel">
        <div className="security-panel__icon"><UserCog /></div>
        <h2>Change password</h2>
        <p>You will be signed out on every device after this change.</p>
        <form onSubmit={submit}>
          <Field label="Current password" name="current-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
          <Field label="New password" name="new-password" type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required />
          <Field label="Confirm new password" name="confirm-password" type="password" minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
          {confirmation && password !== confirmation && <div className="form-error">Passwords do not match.</div>}
          <ErrorMessage error={change.error} />
          <Button busy={change.isPending} disabled={password !== confirmation} type="submit">Change password</Button>
        </form>
      </section>
    </>
  );
}
