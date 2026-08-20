/**
 * SSE client for `GET /api/events` (decision D2).
 *
 * One `EventSource` per session, opened after auth. The backend frames each event
 * with an `event:` name equal to its `type` discriminator, so we listen per type.
 * `: ping` heartbeats are SSE comments — `EventSource` ignores them automatically —
 * and `EventSource` reconnects on transport drop on its own.
 *
 * `withCredentials: true` sends the auth cookie; without it `/api/events` 401s while
 * plain `fetch` POSTs still work (a subtle cross-origin footgun called out in the
 * backend events audit).
 */

import type { StatusEvent, TaskDoneEvent, TaskProgressEvent } from "./types";

export interface EventStreamHandlers {
  onStatus?: (e: StatusEvent) => void;
  onTaskProgress?: (e: TaskProgressEvent) => void;
  onTaskDone?: (e: TaskDoneEvent) => void;
  onOpen?: () => void;
  onError?: (err: Event) => void;
}

/**
 * Open the session event stream. Returns a `close()` to tear it down (call on
 * logout / unmount). Safe to call once per authenticated session.
 */
export function openEventStream(handlers: EventStreamHandlers): () => void {
  const source = new EventSource("/api/events", { withCredentials: true });

  const parse = <T>(ev: MessageEvent): T | null => {
    try {
      return JSON.parse(ev.data) as T;
    } catch {
      return null;
    }
  };

  const onStatus = (ev: MessageEvent) => {
    const data = parse<StatusEvent>(ev);
    if (data) handlers.onStatus?.(data);
  };
  const onTaskProgress = (ev: MessageEvent) => {
    const data = parse<TaskProgressEvent>(ev);
    if (data) handlers.onTaskProgress?.(data);
  };
  const onTaskDone = (ev: MessageEvent) => {
    const data = parse<TaskDoneEvent>(ev);
    if (data) handlers.onTaskDone?.(data);
  };

  source.addEventListener("status", onStatus as EventListener);
  source.addEventListener("task_progress", onTaskProgress as EventListener);
  source.addEventListener("task_done", onTaskDone as EventListener);
  if (handlers.onOpen) source.addEventListener("open", handlers.onOpen);
  // EventSource fires `error` on transient disconnects too (it auto-reconnects);
  // surface it but don't tear down — let the browser retry.
  if (handlers.onError) source.addEventListener("error", handlers.onError);

  return () => {
    source.removeEventListener("status", onStatus as EventListener);
    source.removeEventListener("task_progress", onTaskProgress as EventListener);
    source.removeEventListener("task_done", onTaskDone as EventListener);
    source.close();
  };
}
