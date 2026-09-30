/**
 * Correlate a resumed conversation's artifact catalog with its assistant turns.
 *
 * The catalog in Valkey is conversation-scoped, not per-turn: `GET /api/conversations/{id}`
 * returns every artifact the conversation ever produced, with no link back to the turn
 * that produced it. A live session showed each turn's own artifacts under that turn's
 * reply, so restoring a conversation has to reconstruct the grouping — and the only
 * shared signal is time (`ArtifactMeta.created_at` against `ConversationMessage.timestamp`).
 *
 * Kept as a dependency-free leaf module so it is unit-testable under `node --test`
 * (`chat.ts` itself pulls in the API client and can only run inside Vite).
 */

/** Minimal shape needed from a transcript entry. */
export type TurnLike = {
  role: "user" | "assistant";
  timestamp?: string | null;
};

/** Minimal shape needed from an artifact. */
export type DatedArtifact = {
  created_at?: string | null;
};

/** Epoch ms for an ISO timestamp, or `null` when absent/unparseable. */
function epoch(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const t = Date.parse(ts);
  return Number.isNaN(t) ? null : t;
}

/**
 * Bucket `artifacts` per message, returning one array per entry in `messages`.
 *
 * An artifact belongs to the first assistant turn completed at or after it was created.
 * Artifacts created before the first assistant turn fall to that first turn (user uploads
 * never get here: the backend leaves them out of the detail response); anything created after the last assistant turn — or carrying no usable
 * `created_at` — falls to the last one, which is also where the whole catalog lands when
 * no assistant turn has a usable timestamp. That keeps the previous
 * everything-on-the-last-turn behaviour as the degenerate case while giving a multi-turn
 * conversation the per-turn grouping a live session showed. Buckets for user entries stay
 * empty. Order within a bucket follows `artifacts`.
 */
export function artifactsByAssistantTurn<A extends DatedArtifact>(
  messages: TurnLike[],
  artifacts: A[],
): A[][] {
  const buckets: A[][] = messages.map(() => []);
  const turns = messages
    .map((m, index) => ({ index, at: epoch(m.timestamp) }))
    .filter((t) => messages[t.index].role === "assistant");
  if (!turns.length) return buckets;

  const last = turns[turns.length - 1].index;
  for (const artifact of artifacts) {
    const at = epoch(artifact.created_at);
    const turn = at === null ? undefined : turns.find((t) => t.at !== null && t.at >= at);
    buckets[turn ? turn.index : last].push(artifact);
  }
  return buckets;
}
