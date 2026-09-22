import assert from "node:assert/strict";
import test from "node:test";

import { artifactsByAssistantTurn, type TurnLike } from "./transcriptArtifacts.ts";

const a = (id: string, created_at?: string | null) => ({ id, created_at });

test("splits the catalog across assistant turns by creation time", () => {
  const messages: TurnLike[] = [
    { role: "user", timestamp: "2026-09-22T12:15:41Z" },
    { role: "assistant", timestamp: "2026-09-22T12:20:21Z" },
    { role: "user", timestamp: "2026-09-22T12:21:22Z" },
    { role: "assistant", timestamp: "2026-09-22T12:30:03Z" },
  ];
  // Upload precedes the first reply; then one artifact per turn.
  const artifacts = [
    a("upload", "2026-09-22T12:15:41Z"),
    a("mesh-1", "2026-09-22T12:20:10Z"),
    a("mesh-2", "2026-09-22T12:29:55Z"),
  ];

  const buckets = artifactsByAssistantTurn(messages, artifacts);

  assert.deepEqual(buckets.map((b) => b.map((x) => x.id)), [[], ["upload", "mesh-1"], [], ["mesh-2"]]);
});

test("artifacts created after the last reply fall to the last turn", () => {
  const messages: TurnLike[] = [
    { role: "user", timestamp: "2026-09-22T12:00:00Z" },
    { role: "assistant", timestamp: "2026-09-22T12:01:00Z" },
  ];
  const buckets = artifactsByAssistantTurn(messages, [a("late", "2026-09-22T13:00:00Z")]);
  assert.deepEqual(buckets[1].map((x) => x.id), ["late"]);
});

test("an artifact with no usable created_at falls to the last turn", () => {
  const messages: TurnLike[] = [
    { role: "assistant", timestamp: "2026-09-22T12:01:00Z" },
    { role: "user", timestamp: "2026-09-22T12:02:00Z" },
    { role: "assistant", timestamp: "2026-09-22T12:03:00Z" },
  ];
  const buckets = artifactsByAssistantTurn(messages, [a("x"), a("y", "not-a-date")]);
  assert.deepEqual(buckets.map((b) => b.map((i) => i.id)), [[], [], ["x", "y"]]);
});

test("falls back to everything-on-the-last-turn when timestamps are unusable", () => {
  const messages: TurnLike[] = [
    { role: "user", timestamp: "" },
    { role: "assistant", timestamp: "" },
    { role: "assistant", timestamp: null },
  ];
  const buckets = artifactsByAssistantTurn(messages, [a("p", "2026-09-22T12:00:00Z"), a("q")]);
  assert.deepEqual(buckets.map((b) => b.map((i) => i.id)), [[], [], ["p", "q"]]);
});

test("a transcript with no assistant turn drops nothing into user buckets", () => {
  const buckets = artifactsByAssistantTurn([{ role: "user", timestamp: "2026-09-22T12:00:00Z" }], [a("z")]);
  assert.deepEqual(buckets, [[]]);
});
