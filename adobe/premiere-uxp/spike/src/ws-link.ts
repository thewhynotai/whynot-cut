// The spike's side of the daemon link: a small recorder around a WebSocket (every event kept, nothing assumed) and the
// helpers that keep the engine token out of every result. The probe itself (ws_loopback) lives in probes.ts.

/** What a UXP/browser-style WebSocket offers (property handlers, like the 0.1.0 probe used). */
export interface WsLike {
  readyState: number;
  url?: string;
  protocol?: string;
  extensions?: string;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onclose: ((ev: { code?: number; reason?: string; wasClean?: boolean }) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WsCtor = new (url: string) => WsLike;

export interface WsMessage {
  /** ms since the session was created */
  at_ms: number;
  type: string;
  data: unknown;
  raw_length: number;
}

/** Replace the token (and any 64+ hex run, which is what a token looks like) in text that is about to be recorded. */
export function redact(text: string, token: string): string {
  let out = token ? text.split(token).join("[redacted]") : text;
  out = out.replace(/[0-9a-fA-F]{64,}/g, "[redacted]");
  return out;
}

export const sleepMs = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export function hasOwn(o: unknown, key: string): boolean {
  return typeof o === "object" && o !== null && Object.prototype.hasOwnProperty.call(o, key);
}

/** One connection, recorded: open / messages / errors / close with times, and waiters that resolve on the next event. */
export class WsSession {
  readonly ws: WsLike;
  readonly created = Date.now();
  opened = false;
  openAtMs: number | null = null;
  errorEvents = 0;
  closed: { code: number | null; reason: string; wasClean: boolean | null; at_ms: number } | null = null;
  readonly messages: WsMessage[] = [];
  private used = new Set<WsMessage>();
  private listeners = new Set<() => void>();

  constructor(url: string, Ctor: WsCtor) {
    this.ws = new Ctor(url);
    this.ws.onopen = () => {
      this.opened = true;
      this.openAtMs = Date.now() - this.created;
      this.poke();
    };
    this.ws.onmessage = (ev) => {
      const raw = typeof ev.data === "string" ? ev.data : String(ev.data);
      let type = "(not json)";
      let data: unknown = null;
      try {
        data = JSON.parse(raw);
        const t = (data as { type?: unknown } | null)?.type;
        type = typeof t === "string" ? t : "(no type)";
      } catch {
        // keep "(not json)"
      }
      this.messages.push({ at_ms: Date.now() - this.created, type, data, raw_length: raw.length });
      this.poke();
    };
    this.ws.onerror = () => {
      this.errorEvents++;
      this.poke();
    };
    this.ws.onclose = (ev) => {
      this.closed = { code: typeof ev?.code === "number" ? ev.code : null, reason: typeof ev?.reason === "string" ? ev.reason : "", wasClean: typeof ev?.wasClean === "boolean" ? ev.wasClean : null, at_ms: Date.now() - this.created };
      this.poke();
    };
  }

  private poke(): void {
    for (const l of [...this.listeners]) l();
  }

  /** Resolves with check()'s first non-undefined value (checked now and after every event), or "timeout". */
  wait<T>(check: () => T | undefined, ms: number): Promise<T | "timeout"> {
    const now = check();
    if (now !== undefined) return Promise.resolve(now);
    return new Promise((resolve) => {
      const finish = (v: T | "timeout") => {
        clearTimeout(timer);
        this.listeners.delete(listener);
        resolve(v);
      };
      const listener = () => {
        const v = check();
        if (v !== undefined) finish(v);
      };
      const timer = setTimeout(() => finish("timeout"), ms);
      this.listeners.add(listener);
    });
  }

  /** The first not-yet-consumed message whose type is in `types`, "closed" when the socket closes first, or "timeout". */
  async next(types: string[], ms: number): Promise<WsMessage | "closed" | "timeout"> {
    const got = await this.wait<WsMessage | "closed">(() => {
      const m = this.messages.find((x) => !this.used.has(x) && types.includes(x.type));
      if (m) {
        this.used.add(m);
        return m;
      }
      return this.closed ? "closed" : undefined;
    }, ms);
    return got;
  }

  send(obj: unknown): void {
    this.ws.send(JSON.stringify(obj));
  }

  close(code = 1000, reason = "spike done"): void {
    try {
      this.ws.close(code, reason);
    } catch {
      // already closed
    }
  }

  /** Message types seen since `fromMs`, in order (the log never holds message bodies other than the ones a step reads). */
  typesSince(fromMs: number): string[] {
    return this.messages.filter((m) => m.at_ms >= fromMs).map((m) => m.type);
  }
}
