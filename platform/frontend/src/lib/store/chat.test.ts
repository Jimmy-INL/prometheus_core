// This file is part of Prometheus
// https://inl.gov/super-intelligence/prometheus/
//
// Copyright 2026 Battelle Energy Alliance, LLC
// All rights reserved, see NOTICE.txt for full restrictions
// https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
//
// Licensed under the MIT License, please see LICENSE for details
// https://github.com/idaholab/prometheus_core/blob/main/LICENSE
//
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { register } from "node:module";
import test, { afterEach } from "node:test";

/* The real chat store, with the API client, the SSE client and React stubbed out.
 * A loader hook is needed because the store imports them through the `@/` alias
 * and without extensions, which Node does not resolve by itself; the client also
 * uses constructor parameter properties, which type stripping cannot run. */
const SRC = new URL("../../", import.meta.url).href; // .../frontend/src/
const hooks = `
const SRC = ${JSON.stringify(SRC)};
const STUBS = {
  "@/lib/api/client": "stub:client",
  "@/lib/api/events": "stub:events",
  react: "stub:react",
};
export async function resolve(specifier, context, next) {
  if (STUBS[specifier]) return { url: STUBS[specifier], shortCircuit: true };
  const spec = specifier.startsWith("@/") ? SRC + specifier.slice(2) : specifier;
  const fromTs = context.parentURL && context.parentURL.endsWith(".ts");
  const isRel = spec.startsWith("./") || spec.startsWith("../") || spec.startsWith("file:");
  if ((fromTs || specifier.startsWith("@/")) && isRel && !/\\.[cm]?[jt]sx?$/.test(spec)) {
    return next(spec + ".ts", context);
  }
  return next(spec, context);
}
const SOURCES = {
  "stub:react":
    "export function useSyncExternalStore(sub, get) { globalThis.__chatTestTap = get; return get(); }",
  "stub:events": "export function openEventStream() { return () => {}; }",
  "stub:client": \`
    export class ApiError extends Error {
      constructor(status, message) { super(message); this.status = status; this.name = "ApiError"; }
    }
    export const api = new Proxy({}, { get: (_t, k) => (...a) => globalThis.__chatTestApi[k](...a) });
  \`,
};
export async function load(url, context, next) {
  if (SOURCES[url]) return { format: "module", shortCircuit: true, source: SOURCES[url] };
  return next(url, context);
}
`;
register("data:text/javascript," + encodeURIComponent(hooks));

type Api = Record<string, (...a: unknown[]) => Promise<unknown>>;
const g = globalThis as unknown as {
  __chatTestApi: Api;
  __chatTestTap: () => Record<string, unknown>;
  sessionStorage: unknown;
};

const { chatStore, useChatState: tapChatState } = await import("./chat.ts");
const { ApiError } = (await import("@/lib/api/client" as string)) as {
  ApiError: new (status: number, message: string) => Error;
};
tapChatState(); // not a render: the stubbed hook hands back the store's getSnapshot
const readState = () => g.__chatTestTap();
afterEach(() => chatStore.clear()); // the store is a module singleton

function installStorage(openId: string | null): void {
  const backing = new Map<string, string>();
  if (openId) backing.set("prometheus.openConversationId", openId);
  g.sessionStorage = {
    getItem: (k: string) => backing.get(k) ?? null,
    setItem: (k: string, v: string) => void backing.set(k, v),
    removeItem: (k: string) => void backing.delete(k),
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const tick = () => new Promise((r) => setTimeout(r, 0));
const detail = (id: string) => ({
  conversation_id: id,
  auto_approve_steps: false,
  messages: [{ role: "user", content: "hi" }],
  artifacts: [],
});

test("a resume that lands after suspendForReauth() leaves the store unready, so sign-in resumes again", async () => {
  installStorage("conv-A");
  const stale = deferred<unknown>();
  let resumeCalls = 0;
  g.__chatTestApi = {
    getConfig: async () => ({}),
    resumeConversation: () => {
      resumeCalls += 1;
      return resumeCalls === 1 ? stale.promise : Promise.resolve(detail("conv-A"));
    },
    createSession: async () => ({ conversation_id: "conv-new", auto_approve_steps: false }),
  };

  const boot = chatStore.bootstrap("p");
  await tick();
  chatStore.suspendForReauth();
  stale.resolve(detail("conv-A"));
  await boot;
  assert.equal(readState().ready, false);

  await chatStore.bootstrap("p");
  assert.equal(resumeCalls, 2);
  assert.equal(readState().ready, true);
  assert.equal(readState().conversationId, "conv-A");
});

test("a resume that fails after suspendForReauth() adds no error and leaves the store unready", async () => {
  installStorage("conv-A");
  const stale = deferred<unknown>();
  g.__chatTestApi = {
    getConfig: async () => ({}),
    resumeConversation: () => stale.promise,
    createSession: async () => ({ conversation_id: "conv-new", auto_approve_steps: false }),
  };

  const boot = chatStore.bootstrap("p");
  await tick();
  chatStore.suspendForReauth();
  stale.reject(new ApiError(401, "Not authenticated"));
  await boot;

  assert.equal(readState().ready, false);
  assert.deepEqual(readState().items, []);
});

test("a bootstrap createSession superseded by a sidebar click does not take the conversation", async () => {
  installStorage(null);
  const create = deferred<unknown>();
  g.__chatTestApi = {
    getConfig: async () => ({}),
    createSession: () => create.promise,
    resumeConversation: async () => detail("conv-B"),
  };

  const boot = chatStore.bootstrap("p");
  await tick();
  await chatStore.loadConversation("conv-B");
  create.resolve({ conversation_id: "conv-new", auto_approve_steps: false });
  await boot;

  assert.equal(readState().ready, true);
  assert.equal(readState().conversationId, "conv-B");
});

test("a reload shows the resume marker during getConfig() and drops it when getConfig() fails", async () => {
  installStorage("conv-A");
  const config = deferred<unknown>();
  g.__chatTestApi = { getConfig: () => config.promise };

  const boot = chatStore.bootstrap("p");
  assert.equal(readState().resumingConversationId, "conv-A");
  config.reject(new Error("offline"));
  await boot;

  assert.equal(readState().resumingConversationId, null);
  assert.equal(readState().ready, true);
});
