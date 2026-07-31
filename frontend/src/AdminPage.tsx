import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  BarChart3,
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  Clipboard,
  Gamepad2,
  GripVertical,
  Image as ImageIcon,
  KeyRound,
  Lightbulb,
  ListChecks,
  LockKeyhole,
  LogOut,
  Medal,
  Menu,
  Pencil,
  Plus,
  RotateCcw,
  Shield,
  Trash2,
  Upload,
  UserCog,
  Users,
  Video,
  X,
} from "lucide-react";

import {
  AdminClue,
  AdminGame,
  AdminGameDetail,
  AdminHint,
  AdminUser,
  AuditEvent,
  AuditEventPage,
  ClueMedia,
  api,
  formatDate,
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
    path === "/admin/players" ? <Players me={me} /> :
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
          <div>{initials(me.full_name)}</div>
          <span><strong>{me.full_name}</strong><small>Administrator</small></span>
          <button className="icon-button" onClick={() => logout.mutate()} aria-label="Sign out"><LogOut /></button>
        </div>
      </aside>
      <div className="admin-main">
        <header className="admin-topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu /></button>
          <div><span>Administration</span><strong>PDC Scavenger Hunt</strong></div>
          <span className="admin-topbar__user">{me.email_address}</span>
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
        <Stat icon={<ListChecks />} value={data.data?.completions ?? "—"} label="Clues solved" color="lime" />
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

export function Players({ me }: { me: Me }) {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit-events"] });
    },
  });
  const invite = useMutation({
    mutationFn: (id: string) => postJson<{ setup_url: string }>(`/api/v1/admin/users/${id}/setup-link`, {}),
    onSuccess: (result) => {
      setSetupUrl(result.setup_url);
      queryClient.invalidateQueries({ queryKey: ["admin-audit-events"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api<{ deleted: boolean }>(`/api/v1/admin/users/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["admin-games"] });
      queryClient.invalidateQueries({ queryKey: ["admin-game"] });
    },
  });
  function confirmDelete(user: AdminUser) {
    if (window.confirm(
      `Permanently delete ${user.full_name}? Their game assignments, password invitations, and clue progress will also be deleted. This cannot be undone.`,
    )) {
      remove.mutate(user.id);
    }
  }
  return (
    <>
      <PageTitle eyebrow="People & access" title="Players">
        <Button onClick={() => setCreating(true)}><Plus /> Add player</Button>
      </PageTitle>
      <p className="page-lede">Provision player accounts, manage administrator access, and issue password invitations.</p>
      <section className="panel">
        <ErrorMessage error={update.error || invite.error || remove.error} />
        {users.isLoading ? <div className="panel-loading">Loading players…</div> :
          users.isError ? <ErrorMessage error={users.error} /> :
          !users.data?.length ? <EmptyState icon={<Users />} title="No players">Create the first player to begin.</EmptyState> :
          <div className="table">
            <div className="user-table user-table--head"><span>Player</span><span>Games</span><span>Access</span><span>Status</span><span>Actions</span></div>
            {users.data.map((user) => (
              <div className="user-table" key={user.id}>
                <span className="person-cell"><span className="avatar">{initials(user.full_name)}</span><span><strong>{user.full_name}</strong><small>{user.email_address}</small></span></span>
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
                  {user.id !== me.id && (
                    <Button
                      variant="danger"
                      busy={remove.isPending && remove.variables === user.id}
                      onClick={() => confirmDelete(user)}
                    >
                      <Trash2 /> Delete
                    </Button>
                  )}
                </span>
              </div>
            ))}
          </div>
        }
      </section>
      <AuditLog />
      {creating && <CreatePlayer onClose={() => setCreating(false)} onCreated={(url) => { setCreating(false); setSetupUrl(url); queryClient.invalidateQueries({ queryKey: ["admin-users"] }); queryClient.invalidateQueries({ queryKey: ["admin-audit-events"] }); }} />}
      {editing && <EditPlayer user={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); queryClient.invalidateQueries({ queryKey: ["admin-users"] }); queryClient.invalidateQueries({ queryKey: ["admin-audit-events"] }); }} />}
      {setupUrl && <InviteModal url={setupUrl} onClose={() => setSetupUrl(null)} />}
    </>
  );
}

const auditActionLabels: Record<string, string> = {
  "auth.login_succeeded": "Signed in",
  "auth.login_failed": "Sign-in rejected",
  "auth.logout": "Signed out",
  "auth.password_set": "Set password",
  "auth.password_changed": "Changed password",
  "clue.code_rejected": "Tried an incorrect clue code",
  "clue.completed": "Completed a clue",
  "clue.answer_revealed": "Revealed a clue answer",
  "user.created": "Created a player",
  "user.seeded": "Created the initial administrator",
  "user.updated": "Updated a player",
  "user.deleted": "Deleted a player",
  "user.setup_link_generated": "Issued a password invitation",
  "game.created": "Created a game",
  "game.updated": "Updated a game",
  "game.players_updated": "Changed game assignments",
  "clue.created": "Created a clue",
  "clue.updated": "Updated a clue",
  "clues.reordered": "Reordered clues",
  "clue.deleted": "Deleted a clue",
  "clue.media_attached": "Attached clue media",
  "clue.media_upload_started": "Started a clue media upload",
  "clue.media_replaced": "Replaced clue media",
  "clue.media_removed": "Removed clue media",
  "clue.media_ready": "Finished processing clue media",
  "clue.media_error": "Failed to process clue media",
  "hint.created": "Created hint",
  "hint.updated": "Updated hint",
  "hint.deleted": "Deleted hint",
  "hints.reordered": "Reordered hints",
  "hint.media_attached": "Attached hint media",
  "hint.media_replaced": "Replaced hint media",
  "hint.media_removed": "Removed hint media",
  "hint.media_ready": "Finished processing hint media",
  "hint.media_error": "Failed to process hint media",
  "hint.revealed": "Revealed hint",
  "player.progress_advanced": "Advanced player progress",
  "player.progress_reset": "Reset player progress",
  "player.clue_completed": "Marked a player's clue complete",
  "player.clue_reset": "Reset a player's clue",
};

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function changedFields(event: AuditEvent) {
  if (!event.before || !event.after) return [];
  return Object.keys(event.after).filter(
    (key) => JSON.stringify(event.before?.[key]) !== JSON.stringify(event.after?.[key]),
  );
}

function auditSummary(event: AuditEvent) {
  if (event.reason) return event.reason;
  const after = event.after;
  if (
    (event.action === "clue.completed" ||
      event.action === "clue.answer_revealed") &&
    typeof after?.position === "number"
  ) {
    return `Clue ${after.position}`;
  }
  if (event.action === "hint.revealed" && typeof after?.position === "number") {
    return `Hint ${after.position}`;
  }
  if (event.action === "user.created" && typeof after?.email_address === "string") {
    return after.email_address;
  }
  if ((event.action === "game.created" || event.action === "game.updated") && typeof after?.title === "string") {
    const fields = changedFields(event);
    return fields.length ? `${after.title} · Changed ${fields.map(humanize).join(", ")}` : after.title;
  }
  if (event.action === "user.updated") {
    const fields = changedFields(event);
    return fields.length ? `Changed ${fields.map(humanize).join(", ")}` : "Player record saved";
  }
  if (event.action === "user.deleted" && typeof event.before?.email_address === "string") {
    return event.before.email_address;
  }
  if (event.action === "game.players_updated" && Array.isArray(after?.user_ids)) {
    return `${after.user_ids.length} player${after.user_ids.length === 1 ? "" : "s"} assigned`;
  }
  if (event.action === "clue.created" && typeof after?.position === "number") {
    return `Clue ${after.position}`;
  }
  if (event.action === "clue.updated") {
    const fields = changedFields(event);
    return fields.length ? `Changed ${fields.map(humanize).join(", ")}` : "Clue saved";
  }
  if (event.action === "clues.reordered" && Array.isArray(after?.clue_ids)) {
    return `${after.clue_ids.length} clues`;
  }
  if (event.action === "clue.deleted" && typeof event.before?.position === "number") {
    return `Clue ${event.before.position}`;
  }
  return humanize(event.entity_type);
}

export function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className="table audit-table-wrap">
      <div className="audit-table audit-table--head"><span>When</span><span>Player or admin</span><span>Activity</span><span>Game &amp; details</span></div>
      {events.map((event) => (
        <div className="audit-table" key={event.id}>
          <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
          <span className="audit-actor">
            <strong>{event.actor?.full_name ?? (event.action === "auth.login_failed" ? "Unknown account" : "System")}</strong>
            <small>
              {event.actor?.is_admin ? "Administrator" : event.actor?.email_address ?? "Not authenticated"}
              {event.subject && event.subject.id !== event.actor?.id ? ` · For ${event.subject.full_name}` : ""}
            </small>
          </span>
          <span><strong>{auditActionLabels[event.action] ?? humanize(event.action.replaceAll(".", " "))}</strong></span>
          <span className="audit-summary">
            {event.game && <strong className="audit-game">{event.game.title}</strong>}
            <span>{auditSummary(event)}</span>
            <details>
              <summary>Record details</summary>
              <dl>
                {event.game && <div><dt>Game</dt><dd>{event.game.title} · {event.game.id}</dd></div>}
                <div><dt>Entity</dt><dd>{humanize(event.entity_type)} · {event.entity_id}</dd></div>
                {event.request_id && <div><dt>Request</dt><dd>{event.request_id}</dd></div>}
                {event.before && <div><dt>Before</dt><dd><pre>{JSON.stringify(event.before, null, 2)}</pre></dd></div>}
                {event.after && <div><dt>After</dt><dd><pre>{JSON.stringify(event.after, null, 2)}</pre></dd></div>}
              </dl>
            </details>
          </span>
        </div>
      ))}
    </div>
  );
}

function AuditLog({ gameId }: { gameId?: string }) {
  const pageSize = 50;
  const [offset, setOffset] = useState(0);
  const events = useQuery({
    queryKey: ["admin-audit-events", gameId ?? "general", offset],
    queryFn: () =>
      api<AuditEventPage>(
        `/api/v1/admin/audit-events?limit=${pageSize}&offset=${offset}${
          gameId ? `&game_id=${gameId}` : ""
        }`,
      ),
  });
  const page = Math.floor(offset / pageSize) + 1;
  const pageCount = Math.max(1, Math.ceil((events.data?.total ?? 0) / pageSize));
  return (
    <section className={gameId ? "drawer-section game-audit-panel" : "panel audit-panel"}>
      <header className="audit-panel__head">
        <div>
          <div className="eyebrow">Accountability</div>
          <h2>{gameId ? "Game audit history" : "Player audit trail"}</h2>
          <p>
            {gameId
              ? "Player activity and administrative changes for this game."
              : "Account, login, password, and other activity outside a specific game."}
          </p>
        </div>
        {events.data && <span>{events.data.total} event{events.data.total === 1 ? "" : "s"}</span>}
      </header>
      {events.isLoading ? <div className="panel-loading">Loading audit trail…</div> :
        events.isError ? <ErrorMessage error={events.error} /> :
        !events.data?.items.length ? <EmptyState icon={<Shield />} title="No audit events">Activity will appear here as players and administrators use the hunt.</EmptyState> :
        <>
          <AuditTable events={events.data.items} />
          {pageCount > 1 && (
            <footer className="audit-pagination">
              <Button variant="quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</Button>
              <span>Page {page} of {pageCount}</span>
              <Button variant="quiet" disabled={offset + pageSize >= events.data.total} onClick={() => setOffset(offset + pageSize)}>Next</Button>
            </footer>
          )}
        </>
      }
    </section>
  );
}

function EditPlayer({ user, onClose, onSaved }: { user: AdminUser; onClose: () => void; onSaved: () => void }) {
  const [fullName, setFullName] = useState(user.full_name);
  const [emailAddress, setEmailAddress] = useState(user.email_address);
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [active, setActive] = useState(user.active);
  const save = useMutation({
    mutationFn: () => postJson<AdminUser>(`/api/v1/admin/users/${user.id}`, { full_name: fullName, email_address: emailAddress, is_admin: isAdmin, active }, "PATCH"),
    onSuccess: onSaved,
  });
  return (
    <Modal title="Edit player" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <Field label="Full name" name="edit-full-name" value={fullName} onChange={(event) => setFullName(event.target.value)} required />
        <Field label="Email address" name="edit-email-address" type="email" value={emailAddress} onChange={(event) => setEmailAddress(event.target.value)} required />
        <label className="check-field"><input type="checkbox" checked={isAdmin} onChange={(event) => setIsAdmin(event.target.checked)} /><span><strong>Administrator</strong><small>Can configure games, clues, and players.</small></span></label>
        <label className="check-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span><strong>Active account</strong><small>Inactive users cannot sign in or play.</small></span></label>
        <ErrorMessage error={save.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={save.isPending} type="submit">Save player</Button></div>
      </form>
    </Modal>
  );
}

function CreatePlayer({ onClose, onCreated }: { onClose: () => void; onCreated: (url: string) => void }) {
  const [emailAddress, setEmailAddress] = useState("");
  const [fullName, setFullName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const create = useMutation({
    mutationFn: () => postJson<AdminUser & { setup_url: string }>("/api/v1/admin/users", { email_address: emailAddress, full_name: fullName, is_admin: isAdmin }),
    onSuccess: (result) => onCreated(result.setup_url),
  });
  return (
    <Modal title="Add player" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="Full name" name="full-name" value={fullName} onChange={(event) => setFullName(event.target.value)} required />
        <Field label="Email address" name="email-address" type="email" autoComplete="email" value={emailAddress} onChange={(event) => setEmailAddress(event.target.value)} required />
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
  const [closingMessage, setClosingMessage] = useState("");
  const [allowAnswerReveal, setAllowAnswerReveal] = useState(false);
  const create = useMutation({
    mutationFn: () => postJson<AdminGame>("/api/v1/admin/games", {
      title,
      description: description || null,
      instructions: instructions || null,
      closing_message: closingMessage || null,
      allow_answer_reveal: allowAnswerReveal,
    }),
    onSuccess: onCreated,
  });
  return (
    <Modal title="Create game" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="Game title" name="title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Description" name="description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        <TextArea label="Player instructions" name="instructions" rows={3} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        <TextArea label="Closing message" name="closing-message" rows={3} value={closingMessage} onChange={(event) => setClosingMessage(event.target.value)} hint="Shown after a player solves the final clue." />
        <label className="check-field">
          <input
            type="checkbox"
            checked={allowAnswerReveal}
            onChange={(event) => setAllowAnswerReveal(event.target.checked)}
          />
          <span>
            <strong>Allow answer reveals</strong>
            <small>After revealing every hint—or immediately when there are no hints—a player may reveal the answer. They must still enter the clue code to complete it.</small>
          </span>
        </label>
        <ErrorMessage error={create.error} />
        <div className="modal-actions"><Button variant="quiet" type="button" onClick={onClose}>Cancel</Button><Button busy={create.isPending} type="submit">Create game</Button></div>
      </form>
    </Modal>
  );
}

function SortableClueRow({
  clue,
  index,
  total,
  busy,
  copied,
  onMove,
  onEdit,
  onDelete,
  onCopy,
}: {
  clue: AdminClue;
  index: number;
  total: number;
  busy: boolean;
  copied: boolean;
  onMove: (direction: -1 | 1) => void;
  onEdit: () => void;
  onDelete: () => void;
  onCopy: () => void;
}) {
  const {
    attributes,
    listeners,
    setActivatorNodeRef,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: clue.id, disabled: busy });
  return (
    <article
      className={`clue-admin-row ${isDragging ? "clue-admin-row--dragging" : ""}`}
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <div className="clue-drag-cell">
        <button
          className="clue-drag-handle"
          type="button"
          ref={setActivatorNodeRef}
          disabled={busy}
          aria-label={`Drag clue ${clue.position} to reorder`}
          {...attributes}
          {...listeners}
        >
          <GripVertical aria-hidden="true" />
        </button>
        <span className="clue-position">{clue.position}</span>
      </div>
      <div className="clue-admin-details">
        <strong>{clue.title}</strong>
        <small>{clue.content}</small>
        {clue.code ? (
          <div className="clue-admin-code">
            <span>Code</span>
            <code>{clue.code}</code>
            <button type="button" onClick={onCopy}>
              {copied ? <Check /> : <Clipboard />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        ) : (
          <button className="clue-admin-set-code" type="button" onClick={onEdit}>
            <KeyRound /> Set code
          </button>
        )}
        {(clue.photo || clue.video) && (
          <div className="clue-admin-media">
            {clue.photo && <span><ImageIcon /> Photo</span>}
            {clue.video && <span><Video /> Video</span>}
          </div>
        )}
        {clue.hints.length > 0 && (
          <div className="clue-admin-media">
            <span>
              <Lightbulb /> {clue.hints.length}{" "}
              {clue.hints.length === 1 ? "Hint" : "Hints"}
            </span>
          </div>
        )}
      </div>
      <span className="clue-admin-actions">
        <button className="icon-button" disabled={index === 0 || busy} onClick={() => onMove(-1)} aria-label="Move up"><ChevronUp /></button>
        <button className="icon-button" disabled={index === total - 1 || busy} onClick={() => onMove(1)} aria-label="Move down"><ChevronDown /></button>
        <button className="icon-button" onClick={onEdit} aria-label="Edit clue"><Pencil /></button>
        <button className="icon-button danger-icon" onClick={onDelete} aria-label="Delete clue"><Trash2 /></button>
      </span>
    </article>
  );
}

export function GameEditor({ gameId, onClose }: { gameId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"clues" | "players" | "progress" | "audit">("clues");
  const [editingClue, setEditingClue] = useState<AdminClue | "new" | null>(null);
  const [editingGame, setEditingGame] = useState(false);
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 180, tolerance: 6 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
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
    onMutate: async (clueIds) => {
      await queryClient.cancelQueries({ queryKey: ["admin-game", gameId] });
      const previous = queryClient.getQueryData<AdminGameDetail>(["admin-game", gameId]);
      queryClient.setQueryData<AdminGameDetail>(["admin-game", gameId], (current) => {
        if (!current) return current;
        const cluesById = new Map(current.clues.map((clue) => [clue.id, clue]));
        return {
          ...current,
          clues: clueIds.map((id, index) => ({
            ...cluesById.get(id)!,
            position: index + 1,
          })),
        };
      });
      return { previous };
    },
    onError: (_error, _clueIds, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["admin-game", gameId], context.previous);
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }),
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
  function finishDragging(event: DragEndEvent) {
    if (!detail.data || !event.over || event.active.id === event.over.id) return;
    const oldIndex = detail.data.clues.findIndex((clue) => clue.id === event.active.id);
    const newIndex = detail.data.clues.findIndex((clue) => clue.id === event.over!.id);
    if (oldIndex < 0 || newIndex < 0) return;
    reorder.mutate(
      arrayMove(detail.data.clues, oldIndex, newIndex).map((clue) => clue.id),
    );
  }
  async function copyClueCode(clue: AdminClue) {
    if (!clue.code) {
      setEditingClue(clue);
      return;
    }
    try {
      await navigator.clipboard.writeText(clue.code);
      setCopiedCodeId(clue.id);
      window.setTimeout(() => {
        setCopiedCodeId((current) => current === clue.id ? null : current);
      }, 1600);
    } catch {
      window.prompt("Copy clue code:", clue.code);
    }
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
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit history</button>
        </nav>
        {detail.isLoading ? <div className="panel-loading">Loading game…</div> :
          detail.isError || !detail.data ? <ErrorMessage error={detail.error} /> :
          tab === "clues" ? (
            <div className="drawer-section">
              <div className="drawer-section__title"><div><h3>Clue order</h3><p>Drag clues into display order. Players can choose any clue.</p></div><Button onClick={() => setEditingClue("new")}><Plus /> Add clue</Button></div>
              {!detail.data.clues.length ? <EmptyState icon={<LockKeyhole />} title="No clues">Add the first clue and its unique code.</EmptyState> :
                <DndContext
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragEnd={finishDragging}
                >
                  <SortableContext
                    items={detail.data.clues.map((clue) => clue.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    <div className="clue-admin-list">
                      {detail.data.clues.map((clue, index) => (
                        <SortableClueRow
                          clue={clue}
                          index={index}
                          total={detail.data!.clues.length}
                          busy={reorder.isPending}
                          copied={copiedCodeId === clue.id}
                          key={clue.id}
                          onMove={(direction) => move(index, direction)}
                          onEdit={() => setEditingClue(clue)}
                          onCopy={() => copyClueCode(clue)}
                          onDelete={() => {
                            if (window.confirm(`Delete clue ${clue.position}? Player completions for it will also be removed.`)) {
                              remove.mutate(clue.id);
                            }
                          }}
                        />
                      ))}
                    </div>
                  </SortableContext>
                </DndContext>
              }
            </div>
          ) : tab === "players" ? (
            <MembershipEditor game={detail.data} users={users.data ?? []} />
          ) : tab === "progress" ? (
            <ProgressEditor game={detail.data} />
          ) : (
            <AuditLog gameId={gameId} />
          )
        }
        {editingClue && <ClueEditor gameId={gameId} clue={editingClue === "new" ? null : editingClue} onClose={() => setEditingClue(null)} onSaved={() => { setEditingClue(null); queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }); }} />}
        {editingGame && detail.data && <GameDetailsEditor game={detail.data} onClose={() => setEditingGame(false)} onSaved={() => { setEditingGame(false); queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] }); queryClient.invalidateQueries({ queryKey: ["admin-games"] }); }} />}
      </section>
    </div>
  );
}

export function ProgressEditor({ game }: { game: AdminGameDetail }) {
  const [adjustment, setAdjustment] = useState<{
    entry: AdminGameDetail["players"][number];
    clue: AdminClue;
    completed: boolean;
  } | null>(null);
  return (
    <div className="drawer-section">
      <div className="drawer-section__title"><div><h3>Player progress</h3><p>Each clue can be adjusted independently. Finishers are ranked when all clues are complete; times are shown in Eastern Time.</p></div></div>
      {!game.players.length ? <EmptyState icon={<Users />} title="No assigned players">Assign players to begin tracking progress.</EmptyState> :
        <div className="progress-list">{game.players.map((entry) => (
          <article className="progress-player" key={entry.user.id}>
            <div className="progress-player__summary">
              <span className="avatar">{initials(entry.user.full_name)}</span>
              <span className="progress-player__identity"><strong>{entry.user.full_name}</strong><small>{entry.user.email_address}</small></span>
              {entry.completion_rank && (
                <span
                  className={`finish-rank finish-rank--${rankStyle(entry.completion_rank)}`}
                  aria-label={`${ordinal(entry.completion_rank)} place`}
                  title={entry.finished_at ? `Finished ${formatDate(entry.finished_at)}` : undefined}
                >
                  {entry.completion_rank <= 3 ? <Medal aria-hidden="true" /> : <b>#{entry.completion_rank}</b>}
                  <span><strong>{ordinal(entry.completion_rank)}</strong><small>place</small></span>
                </span>
              )}
              <div className="clue-progress">
                <div
                  className="clue-progress__segments"
                  role="img"
                  aria-label={`${entry.completed_count} of ${game.clue_count} clues complete`}
                >
                  {game.clues.map((clue) => (
                    <span
                      className={entry.completed_clue_ids.includes(clue.id) ? "clue-progress__segment--completed" : undefined}
                      title={`Clue ${clue.position}: ${entry.completed_clue_ids.includes(clue.id) ? "complete" : "incomplete"}`}
                      key={clue.id}
                    />
                  ))}
                </div>
                <small>{entry.completed_count} / {game.clue_count}</small>
              </div>
            </div>
            {game.clues.length > 0 ? (
              <ol className="clue-progress-list">
                {game.clues.map((clue) => {
                  const completion = entry.completions.find((item) => item.clue_id === clue.id);
                  return (
                    <li className={completion ? "clue-progress-list__item--completed" : undefined} key={clue.id}>
                      <span className="clue-progress-list__marker">
                        {completion ? <Check /> : clue.position}
                      </span>
                      <span className="clue-progress-list__clue">
                        <small>Clue {clue.position}</small>
                        <strong>{clue.title}</strong>
                      </span>
                      {completion ? (
                        <time dateTime={completion.completed_at}><Clock3 /> {formatDate(completion.completed_at)}</time>
                      ) : (
                        <span className="clue-progress-list__status">Incomplete</span>
                      )}
                      <Button
                        type="button"
                        variant={completion ? "quiet" : "primary"}
                        onClick={() => setAdjustment({ entry, clue, completed: Boolean(completion) })}
                      >
                        {completion ? <><RotateCcw /> Reset clue</> : <><Check /> Mark complete</>}
                      </Button>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="progress-player__empty">This game has no clues yet.</p>
            )}
          </article>
        ))}</div>
      }
      {adjustment && (
        <ClueProgressEditor
          game={game}
          {...adjustment}
          onClose={() => setAdjustment(null)}
        />
      )}
    </div>
  );
}

function ClueProgressEditor({
  game,
  entry,
  clue,
  completed,
  onClose,
}: {
  game: AdminGameDetail;
  entry: AdminGameDetail["players"][number];
  clue: AdminClue;
  completed: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const adjustment = useMutation({
    mutationFn: () =>
      postJson(
        `/api/v1/admin/game-players/${entry.membership_id}/progress`,
        { reason, clue_id: clue.id },
        completed ? "DELETE" : "PUT",
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-game", game.id] });
      onClose();
    },
  });
  return (
    <Modal title={`${completed ? "Reset" : "Complete"} clue ${clue.position} for ${entry.user.full_name}`} onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); adjustment.mutate(); }}>
        <p>
          {completed
            ? `This resets “${clue.title}” only. Other clues keep their current status. This clue’s revealed hints and answer will also be cleared.`
            : `This marks “${clue.title}” complete now. Other clues keep their current status.`}
        </p>
        <TextArea
          label="Reason"
          name="clue-progress-reason"
          rows={3}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          required
          minLength={3}
          maxLength={500}
          hint="Required for the audit log."
        />
        <ErrorMessage error={adjustment.error} />
        <div className="modal-actions">
          <Button variant="quiet" type="button" onClick={onClose}>Cancel</Button>
          <Button variant={completed ? "danger" : "primary"} busy={adjustment.isPending} type="submit">
            {completed ? <><RotateCcw /> Reset clue</> : <><Check /> Mark complete</>}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function rankStyle(rank: number): "gold" | "silver" | "bronze" | "numbered" {
  return rank === 1 ? "gold" : rank === 2 ? "silver" : rank === 3 ? "bronze" : "numbered";
}

function ordinal(value: number): string {
  const lastTwoDigits = value % 100;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 13) return `${value}th`;
  const suffix = value % 10 === 1 ? "st" : value % 10 === 2 ? "nd" : value % 10 === 3 ? "rd" : "th";
  return `${value}${suffix}`;
}

function GameDetailsEditor({ game, onClose, onSaved }: { game: AdminGameDetail; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(game.title);
  const [description, setDescription] = useState(game.description ?? "");
  const [instructions, setInstructions] = useState(game.instructions ?? "");
  const [closingMessage, setClosingMessage] = useState(game.closing_message ?? "");
  const [allowAnswerReveal, setAllowAnswerReveal] = useState(game.allow_answer_reveal);
  const save = useMutation({
    mutationFn: () => postJson(`/api/v1/admin/games/${game.id}`, {
      title,
      description: description || null,
      instructions: instructions || null,
      closing_message: closingMessage || null,
      allow_answer_reveal: allowAnswerReveal,
    }, "PATCH"),
    onSuccess: onSaved,
  });
  return (
    <Modal title="Edit game details" onClose={onClose}>
      <form className="modal-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <Field label="Game title" name="edit-game-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Description" name="edit-game-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        <TextArea label="Player instructions" name="edit-game-instructions" rows={3} value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        <TextArea label="Closing message" name="edit-game-closing-message" rows={3} value={closingMessage} onChange={(event) => setClosingMessage(event.target.value)} hint="Shown after a player solves the final clue." />
        <label className="check-field">
          <input
            type="checkbox"
            checked={allowAnswerReveal}
            onChange={(event) => setAllowAnswerReveal(event.target.checked)}
          />
          <span>
            <strong>Allow answer reveals</strong>
            <small>Players can reveal an answer after using all available hints, but must still submit the clue code.</small>
          </span>
        </label>
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
        <label key={user.id}><input type="checkbox" checked={selected.has(user.id)} onChange={() => toggle(user.id)} /><span className="avatar">{initials(user.full_name)}</span><span><strong>{user.full_name}</strong><small>{user.email_address}{user.is_admin ? " · Admin" : ""}</small></span></label>
      ))}</div>
    </div>
  );
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function MediaAttachmentEditor({
  owner,
  ownerType,
  ownerLabel,
  onChanged,
}: {
  owner: Pick<AdminClue | AdminHint, "id" | "photo" | "video">;
  ownerType: "clues" | "hints";
  ownerLabel: "clue" | "hint";
  onChanged: (
    mediaType: "photo" | "video",
    media: ClueMedia | null,
  ) => void;
}) {
  const [photo, setPhoto] = useState<ClueMedia | null>(owner.photo);
  const [video, setVideo] = useState<ClueMedia | null>(owner.video);
  const [selectionError, setSelectionError] = useState<Error | null>(null);
  const upload = useMutation({
    mutationFn: async ({
      mediaType,
      file,
    }: {
      mediaType: "photo" | "video";
      file: File;
    }) => {
      const path = `/api/v1/admin/${ownerType}/${owner.id}/media/${mediaType}`;
      return api<ClueMedia>(path, {
        method: "PUT",
        body: file,
        headers: {
          "Content-Type": file.type,
          "X-File-Name": encodeURIComponent(file.name),
        },
      });
    },
    onSuccess: (media) => {
      if (media.media_type === "photo") setPhoto(media);
      else setVideo(media);
      onChanged(media.media_type, media);
    },
  });
  const remove = useMutation({
    mutationFn: (mediaType: "photo" | "video") =>
      api(`/api/v1/admin/${ownerType}/${owner.id}/media/${mediaType}`, {
        method: "DELETE",
      }),
    onSuccess: (_result, mediaType) => {
      if (mediaType === "photo") setPhoto(null);
      else setVideo(null);
      onChanged(mediaType, null);
    },
  });

  function chooseMedia(mediaType: "photo" | "video", file?: File) {
    if (!file) return;
    const maxBytes = mediaType === "photo" ? 8 * 1024 * 1024 : 100 * 1024 * 1024;
    if (file.size > maxBytes) {
      setSelectionError(
        new Error(
          `${mediaType === "photo" ? "Photos" : "Videos"} cannot exceed ${
            mediaType === "photo" ? 8 : 100
          } MiB`,
        ),
      );
      return;
    }
    setSelectionError(null);
    upload.mutate({ mediaType, file });
  }

  function removeMedia(mediaType: "photo" | "video") {
    if (window.confirm(`Remove this ${ownerLabel}'s ${mediaType}?`)) {
      remove.mutate(mediaType);
    }
  }

  return (
    <section className="media-editor">
      <div>
        <strong>Photo</strong>
        <small>JPEG, PNG, or WebP · maximum 8 MiB</small>
        {photo && (
          <div className="media-editor__preview">
            <img src={photo.url} alt="" />
            <span>{photo.original_filename} · {formatFileSize(photo.size_bytes)}</span>
          </div>
        )}
        <div className="media-editor__actions">
          <label className="button button--secondary media-upload-button">
            <Upload /> {photo ? "Replace photo" : "Upload photo"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={upload.isPending}
              onChange={(event) => {
                chooseMedia("photo", event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {photo && <Button type="button" variant="danger" busy={remove.isPending} onClick={() => removeMedia("photo")}>Remove</Button>}
        </div>
      </div>
      <div>
        <strong>Video</strong>
        <small>MP4 or MOV · maximum 100 MiB</small>
        {video && (
          <div className="media-editor__preview">
            {video.status === "ready" ? (
              <iframe
                src={video.url}
                title={`Preview of ${video.original_filename ?? `${ownerLabel} video`}`}
                allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <p>
                {video.status === "error"
                  ? "Cloudflare could not process this video."
                  : "Cloudflare is processing this video. It will appear for players when ready."}
              </p>
            )}
            <span>{video.original_filename} · {formatFileSize(video.size_bytes)}</span>
          </div>
        )}
        <div className="media-editor__actions">
          <label className="button button--secondary media-upload-button">
            <Upload /> {video ? "Replace video" : "Upload video"}
            <input
              type="file"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              disabled={upload.isPending}
              onChange={(event) => {
                chooseMedia("video", event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {video && <Button type="button" variant="danger" busy={remove.isPending} onClick={() => removeMedia("video")}>Remove</Button>}
        </div>
      </div>
      {upload.isPending && <p className="media-editor__status">Uploading media… Keep this window open.</p>}
      <ErrorMessage error={selectionError || upload.error || remove.error} />
    </section>
  );
}

function HintEditor({
  hint,
  onClose,
  onSaved,
  onMediaChanged,
}: {
  hint: AdminHint;
  onClose: () => void;
  onSaved: (hint: AdminHint) => void;
  onMediaChanged: (
    hintId: string,
    mediaType: "photo" | "video",
    media: ClueMedia | null,
  ) => void;
}) {
  const [text, setText] = useState(hint.text ?? "");
  const save = useMutation({
    mutationFn: () =>
      postJson<AdminHint>(
        `/api/v1/admin/hints/${hint.id}`,
        { text: text || null },
        "PATCH",
      ),
    onSuccess: onSaved,
  });
  return (
    <Modal title={`Edit hint ${hint.position}`} onClose={onClose}>
      <div className="modal-form">
        <TextArea
          label="Hint text"
          name={`hint-text-${hint.id}`}
          rows={4}
          value={text}
          onChange={(event) => setText(event.target.value)}
          hint="Optional when the hint includes a photo or video."
        />
        <MediaAttachmentEditor
          owner={hint}
          ownerType="hints"
          ownerLabel="hint"
          onChanged={(mediaType, media) =>
            onMediaChanged(hint.id, mediaType, media)
          }
        />
        <ErrorMessage error={save.error} />
        <div className="modal-actions">
          <Button variant="quiet" type="button" onClick={onClose}>Cancel</Button>
          <Button
            busy={save.isPending}
            type="button"
            onClick={() => save.mutate()}
          >
            Save hint
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function DraftHintMediaEditor({
  photo,
  video,
  disabled,
  onChange,
}: {
  photo: File | null;
  video: File | null;
  disabled: boolean;
  onChange: (mediaType: "photo" | "video", file: File | null) => void;
}) {
  const [selectionError, setSelectionError] = useState<Error | null>(null);

  function chooseMedia(mediaType: "photo" | "video", file?: File) {
    if (!file) return;
    const maxBytes = mediaType === "photo" ? 8 * 1024 * 1024 : 100 * 1024 * 1024;
    if (file.size > maxBytes) {
      setSelectionError(
        new Error(
          `${mediaType === "photo" ? "Photos" : "Videos"} cannot exceed ${
            mediaType === "photo" ? 8 : 100
          } MiB`,
        ),
      );
      return;
    }
    setSelectionError(null);
    onChange(mediaType, file);
  }

  return (
    <section className="media-editor">
      <div>
        <strong>Photo</strong>
        <small>JPEG, PNG, or WebP · maximum 8 MiB</small>
        {photo && (
          <div className="media-editor__preview">
            <span>Ready to upload: {photo.name} · {formatFileSize(photo.size)}</span>
          </div>
        )}
        <div className="media-editor__actions">
          <label className="button button--secondary media-upload-button">
            <Upload /> {photo ? "Replace photo" : "Choose photo"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="Hint photo"
              disabled={disabled}
              onChange={(event) => {
                chooseMedia("photo", event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {photo && (
            <Button
              type="button"
              variant="danger"
              disabled={disabled}
              onClick={() => onChange("photo", null)}
            >
              Remove
            </Button>
          )}
        </div>
      </div>
      <div>
        <strong>Video</strong>
        <small>MP4 or MOV · maximum 100 MiB</small>
        {video && (
          <div className="media-editor__preview">
            <span>Ready to upload: {video.name} · {formatFileSize(video.size)}</span>
          </div>
        )}
        <div className="media-editor__actions">
          <label className="button button--secondary media-upload-button">
            <Upload /> {video ? "Replace video" : "Choose video"}
            <input
              type="file"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              aria-label="Hint video"
              disabled={disabled}
              onChange={(event) => {
                chooseMedia("video", event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {video && (
            <Button
              type="button"
              variant="danger"
              disabled={disabled}
              onClick={() => onChange("video", null)}
            >
              Remove
            </Button>
          )}
        </div>
      </div>
      <ErrorMessage error={selectionError} />
    </section>
  );
}

function NewHintEditor({
  clueId,
  position,
  onClose,
  onSaved,
}: {
  clueId: string;
  position: number;
  onClose: () => void;
  onSaved: (hint: AdminHint) => void;
}) {
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [video, setVideo] = useState<File | null>(null);
  const [persistedHint, setPersistedHint] = useState<AdminHint | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      let hint = persistedHint;
      if (hint) {
        hint = await postJson<AdminHint>(
          `/api/v1/admin/hints/${hint.id}`,
          { text: text || null },
          "PATCH",
        );
      } else {
        hint = await postJson<AdminHint>(
          `/api/v1/admin/clues/${clueId}/hints`,
          { text: text || null },
        );
      }
      setPersistedHint(hint);

      for (const [mediaType, file] of [
        ["photo", photo],
        ["video", video],
      ] as const) {
        if (!file) continue;
        const media: ClueMedia = await api<ClueMedia>(
          `/api/v1/admin/hints/${hint.id}/media/${mediaType}`,
          {
            method: "PUT",
            body: file,
            headers: {
              "Content-Type": file.type,
              "X-File-Name": encodeURIComponent(file.name),
            },
          },
        );
        hint = { ...hint, [mediaType]: media };
        setPersistedHint(hint);
      }
      return hint;
    },
    onSuccess: onSaved,
  });
  const discard = useMutation({
    mutationFn: () =>
      api(`/api/v1/admin/hints/${persistedHint!.id}`, { method: "DELETE" }),
    onSuccess: onClose,
  });
  const hasContent = Boolean(text.trim() || photo || video);

  function close() {
    if (save.isPending || discard.isPending) return;
    if (persistedHint) discard.mutate();
    else onClose();
  }

  return (
    <Modal title={`Add hint ${position}`} onClose={close}>
      <div className="modal-form">
        <TextArea
          label="Hint text"
          name={`new-hint-text-${clueId}`}
          rows={4}
          value={text}
          disabled={save.isPending || discard.isPending}
          onChange={(event) => setText(event.target.value)}
          hint="Optional when the hint includes a photo or video."
        />
        <DraftHintMediaEditor
          photo={photo}
          video={video}
          disabled={save.isPending || discard.isPending}
          onChange={(mediaType, file) => {
            if (mediaType === "photo") setPhoto(file);
            else setVideo(file);
          }}
        />
        {save.isPending && (
          <p className="media-editor__status">
            Saving the hint and uploading its media… Keep this window open.
          </p>
        )}
        <ErrorMessage error={save.error || discard.error} />
        <div className="modal-actions">
          <Button
            variant="quiet"
            type="button"
            busy={discard.isPending}
            disabled={save.isPending}
            onClick={close}
          >
            Cancel
          </Button>
          <Button
            busy={save.isPending}
            disabled={!hasContent || discard.isPending}
            type="button"
            onClick={() => save.mutate()}
          >
            Create hint
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function SortableHintRow({
  hint,
  index,
  total,
  busy,
  onMove,
  onEdit,
  onDelete,
}: {
  hint: AdminHint;
  index: number;
  total: number;
  busy: boolean;
  onMove: (direction: -1 | 1) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const {
    attributes,
    listeners,
    setActivatorNodeRef,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: hint.id, disabled: busy });
  return (
    <article
      className={`hint-admin-row ${isDragging ? "hint-admin-row--dragging" : ""}`}
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <div className="hint-drag-cell">
        <button
          className="clue-drag-handle"
          type="button"
          ref={setActivatorNodeRef}
          disabled={busy}
          aria-label={`Drag hint ${hint.position} to reorder`}
          {...attributes}
          {...listeners}
        >
          <GripVertical aria-hidden="true" />
        </button>
        <span className="hint-admin-position">{hint.position}</span>
      </div>
      <span className="hint-admin-copy">
        <strong>{hint.text || "Media-only hint"}</strong>
        <small>
          {[
            hint.text && "Text",
            hint.photo && "Photo",
            hint.video && "Video",
          ].filter(Boolean).join(" · ") || "No content yet"}
        </small>
      </span>
      <span className="hint-admin-actions">
        <button
          className="icon-button"
          type="button"
          disabled={index === 0 || busy}
          onClick={() => onMove(-1)}
          aria-label={`Move hint ${hint.position} up`}
        >
          <ChevronUp />
        </button>
        <button
          className="icon-button"
          type="button"
          disabled={index === total - 1 || busy}
          onClick={() => onMove(1)}
          aria-label={`Move hint ${hint.position} down`}
        >
          <ChevronDown />
        </button>
        <button
          className="icon-button"
          type="button"
          onClick={onEdit}
          aria-label={`Edit hint ${hint.position}`}
        >
          <Pencil />
        </button>
        <button
          className="icon-button danger-icon"
          type="button"
          onClick={onDelete}
          aria-label={`Delete hint ${hint.position}`}
        >
          <Trash2 />
        </button>
      </span>
    </article>
  );
}

export function HintsEditor({
  clue,
  onChanged,
}: {
  clue: AdminClue;
  onChanged: () => void;
}) {
  const [hints, setHints] = useState(clue.hints);
  const [editing, setEditing] = useState<AdminHint | null>(null);
  const [creating, setCreating] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 180, tolerance: 6 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const reorder = useMutation({
    mutationFn: ({
      hintIds,
    }: {
      hintIds: string[];
      previous: AdminHint[];
    }) =>
      postJson(`/api/v1/admin/clues/${clue.id}/hints/reorder`, {
        hint_ids: hintIds,
      }),
    onError: (_error, variables) => setHints(variables.previous),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: (hintId: string) =>
      api(`/api/v1/admin/hints/${hintId}`, { method: "DELETE" }),
    onSuccess: (_result, hintId) => {
      setHints((current) =>
        current
          .filter((hint) => hint.id !== hintId)
          .map((hint, index) => ({ ...hint, position: index + 1 })),
      );
      onChanged();
    },
  });

  function saveOrder(next: AdminHint[]) {
    const positioned = next.map((hint, hintIndex) => ({
      ...hint,
      position: hintIndex + 1,
    }));
    setHints(positioned);
    reorder.mutate({
      hintIds: positioned.map((hint) => hint.id),
      previous: hints,
    });
  }

  function move(index: number, direction: -1 | 1) {
    saveOrder(arrayMove(hints, index, index + direction));
  }

  function finishDragging(event: DragEndEvent) {
    if (!event.over || event.active.id === event.over.id) return;
    const oldIndex = hints.findIndex((hint) => hint.id === event.active.id);
    const newIndex = hints.findIndex((hint) => hint.id === event.over!.id);
    if (oldIndex < 0 || newIndex < 0) return;
    saveOrder(arrayMove(hints, oldIndex, newIndex));
  }

  function updateHint(updated: AdminHint) {
    setHints((current) =>
      current.map((hint) => hint.id === updated.id ? updated : hint),
    );
    setEditing(null);
    onChanged();
  }

  function updateHintMedia(
    hintId: string,
    mediaType: "photo" | "video",
    media: ClueMedia | null,
  ) {
    setHints((current) =>
      current.map((hint) =>
        hint.id === hintId ? { ...hint, [mediaType]: media } : hint,
      ),
    );
    setEditing((current) =>
      current?.id === hintId ? { ...current, [mediaType]: media } : current,
    );
    onChanged();
  }

  return (
    <section className="hint-editor">
      <header>
        <div>
          <strong><Lightbulb /> Player hints</strong>
          <small>Drag hints into the order players will reveal them.</small>
        </div>
      </header>
      {hints.length > 0 && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={finishDragging}
        >
          <SortableContext
            items={hints.map((hint) => hint.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="hint-admin-list">
              {hints.map((hint, index) => (
                <SortableHintRow
                  hint={hint}
                  index={index}
                  total={hints.length}
                  busy={reorder.isPending}
                  key={hint.id}
                  onMove={(direction) => move(index, direction)}
                  onEdit={() => setEditing(hint)}
                  onDelete={() => {
                    if (window.confirm(`Delete hint ${hint.position}?`)) {
                      remove.mutate(hint.id);
                    }
                  }}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
      <div className="hint-editor__add">
        <p>Add text, a photo, a video, or any combination in one step.</p>
        <Button
          type="button"
          variant="secondary"
          onClick={() => setCreating(true)}
        >
          <Plus /> Add hint
        </Button>
      </div>
      <ErrorMessage error={reorder.error || remove.error} />
      {creating && (
        <NewHintEditor
          clueId={clue.id}
          position={hints.length + 1}
          onClose={() => setCreating(false)}
          onSaved={(hint) => {
            setHints((current) => [...current, hint]);
            setCreating(false);
            onChanged();
          }}
        />
      )}
      {editing && (
        <HintEditor
          hint={editing}
          onClose={() => setEditing(null)}
          onSaved={updateHint}
          onMediaChanged={updateHintMedia}
        />
      )}
    </section>
  );
}

function ClueEditor({ gameId, clue, onClose, onSaved }: { gameId: string; clue: AdminClue | null; onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(clue?.title ?? "");
  const [content, setContent] = useState(clue?.content ?? "");
  const [code, setCode] = useState(clue?.code ?? "");
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
        <Field label="Clue" name="clue-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
        <TextArea label="Answer" name="content" rows={5} value={content} onChange={(event) => setContent(event.target.value)} required />
        <Field
          label={clue ? "Code" : "Unique code"}
          name="code"
          autoComplete="off"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          required={!clue}
          hint={
            clue?.code
              ? "Codes are case-insensitive. Edit this value to replace it."
              : clue
                ? "This legacy code cannot be recovered. Enter a replacement to make it visible here."
                : "Codes are case-insensitive and cannot be reused."
          }
        />
        {clue ? (
          <>
            <MediaAttachmentEditor
              owner={clue}
              ownerType="clues"
              ownerLabel="clue"
              onChanged={() =>
                queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] })
              }
            />
            <HintsEditor
              clue={clue}
              onChanged={() =>
                queryClient.invalidateQueries({ queryKey: ["admin-game", gameId] })
              }
            />
          </>
        ) : (
          <p className="media-editor__new-note">
            Save this clue, then reopen it to attach a photo or video.
          </p>
        )}
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
