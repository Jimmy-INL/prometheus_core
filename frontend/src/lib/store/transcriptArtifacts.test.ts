import assert from "node:assert/strict";
import test from "node:test";

import { artifactsPerTurn, type TurnLike } from "./transcriptArtifacts.ts";

const a = (artifact_id: string) => ({ artifact_id });
const ids = (turns: { artifact_id: string }[][]) => turns.map((t) => t.map((x) => x.artifact_id));

test("each turn gets exactly the artifacts it produced", () => {
  const messages: TurnLike[] = [
    { role: "user" },
    { role: "assistant", artifact_ids: ["mesh-1"] },
    { role: "user" },
    { role: "assistant", artifact_ids: ["mesh-2", "plot"] },
  ];

  const turns = artifactsPerTurn(messages, [a("plot"), a("mesh-1"), a("mesh-2")]);

  assert.deepEqual(ids(turns), [[], ["mesh-1"], [], ["mesh-2", "plot"]]);
});

test("catalog entries no turn produced are not rendered anywhere", () => {
  // The catalog is state for future turns, not a rendering fallback.
  const messages: TurnLike[] = [{ role: "user" }, { role: "assistant", artifact_ids: ["gen"] }];

  const turns = artifactsPerTurn(messages, [a("gen"), a("from-another-turn"), a("unowned")]);

  assert.deepEqual(ids(turns), [[], ["gen"]]);
});

test("an id missing from the catalog (a user upload) is skipped", () => {
  const messages: TurnLike[] = [{ role: "assistant", artifact_ids: ["upload", "gen"] }];

  assert.deepEqual(ids(artifactsPerTurn(messages, [a("gen")])), [["gen"]]);
});

test("a turn stored before ids were recorded shows no artifacts", () => {
  const messages: TurnLike[] = [
    { role: "user" },
    { role: "assistant" },
    { role: "assistant", artifact_ids: null },
    { role: "assistant", artifact_ids: [] },
  ];

  assert.deepEqual(ids(artifactsPerTurn(messages, [a("x")])), [[], [], [], []]);
});

test("user turns stay empty and a repeated id renders once", () => {
  const messages: TurnLike[] = [
    { role: "user", artifact_ids: ["x"] },
    { role: "assistant", artifact_ids: ["x", "x"] },
  ];

  assert.deepEqual(ids(artifactsPerTurn(messages, [a("x")])), [[], ["x"]]);
});
