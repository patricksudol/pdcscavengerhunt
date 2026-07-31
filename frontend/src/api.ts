export type GameStatus = "draft" | "open" | "closed";

export interface Me {
  id: string;
  email_address: string;
  full_name: string;
  is_admin: boolean;
  csrf_token: string;
}

export interface PlayerGame {
  id: string;
  title: string;
  description: string | null;
  status: Exclude<GameStatus, "draft">;
  clue_count: number;
  completed_count: number;
}

export interface PlayerClue {
  id: string;
  position: number;
  status: "completed" | "available";
  clue: string;
  answer?: string;
  completed_at?: string;
  photo?: ClueMedia | null;
  video?: ClueMedia | null;
  hints: PlayerHint[];
}

export interface PlayerHint {
  id?: string;
  position: number;
  status: "revealed" | "available" | "locked";
  text?: string | null;
  photo?: ClueMedia | null;
  video?: ClueMedia | null;
}

export interface PlayerGameDetail extends PlayerGame {
  instructions: string | null;
  closing_message: string | null;
  complete: boolean;
  clues: PlayerClue[];
}

export interface AdminUser {
  id: string;
  email_address: string;
  full_name: string;
  is_admin: boolean;
  active: boolean;
  password_set: boolean;
  created_at: string;
  last_login_at: string | null;
  game_count?: number;
}

export interface AuditActor {
  id: string;
  email_address: string;
  full_name: string;
  is_admin: boolean;
}

export interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string;
  actor: AuditActor | null;
  subject: AuditActor | null;
}

export interface AuditEventPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminGame {
  id: string;
  title: string;
  description: string | null;
  instructions: string | null;
  closing_message: string | null;
  status: GameStatus;
  player_count: number;
  clue_count: number;
  completion_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminClue {
  id: string;
  position: number;
  title: string;
  content: string;
  code: string | null;
  code_set: boolean;
  photo: ClueMedia | null;
  video: ClueMedia | null;
  hints: AdminHint[];
}

export interface AdminHint {
  id: string;
  position: number;
  text: string | null;
  photo: ClueMedia | null;
  video: ClueMedia | null;
}

export interface ClueMedia {
  id: string;
  media_type: "photo" | "video";
  original_filename?: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "error";
  url: string;
  created_at?: string;
}

export interface AdminGameDetail extends AdminGame {
  clues: AdminClue[];
  players: {
    membership_id: string;
    user: AdminUser;
    completed_count: number;
    completed_clue_ids: string[];
    completion_rank: number | null;
    finished_at: string | null;
    completions: {
      clue_id: string;
      completed_at: string;
    }[];
  }[];
}

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.message ?? "Something went wrong",
      body?.details,
    );
  }
  return body as T;
}

export function postJson<T>(path: string, body: unknown, method = "POST") {
  return api<T>(path, { method, body: JSON.stringify(body) });
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/New_York",
  }).format(new Date(value));
}
