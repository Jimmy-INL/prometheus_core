/**
 * src/lib/chainlit/chainlit.ts
 *
 * Chainlit wire-format → Prometheus internal model.
 *
 * This is the single translation layer between raw IStep/IElement data from
 * @chainlit/react-client and what UI components actually render. All message-
 * tree logic belongs here. Components program against FlatItem, not IStep.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * IMPLEMENTATION STATUS
 *
 * Working:
 *   ✓ user_message rendering
 *   ✓ assistant_message rendering (text/markdown only)
 *   ✓ tool step rendering (collapsible status + history)
 *   ✓ ask_action (AskActionMessage approve/reject buttons)
 *   ✓ ask_form (AskElementMessage — DynamicForm)
 *   ✓ elements[] on IStepExtended — wired to ElementList in Chat.tsx
 *   ✓ element pipeline — classifyElement() + VIEWER_REGISTRY in elements.ts
 *   ✓ element fallback — non-custom unregistered kinds show download card;
 *                        custom elements without a registered viewer are hidden
 *   ✓ viewers — PDF, Image, FollowUpSuggestions, PlanViewer
 *   ✓ file upload UI — Paperclip button + multi-file picker, IFileRef wiring
 *
 * Not yet implemented:
 *   ✗ ask_plain (AskUserMessage)
 *   ✗ viewers — IFC, Exodus, file download, JSON, Mermaid, ThermalAnalysis
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { IStep, IAction } from "@chainlit/react-client";
import type { AnyElement } from "./elements";

// ---------------------------------------------------------------------------
// IStep extension
//
// @chainlit/react-client 0.4.2 types IStep with most fields but omits some
// that arrive over the wire from Chainlit 2.x backends. We extend locally
// rather than casting to any throughout the codebase.
//
// waitForAnswer: renamed from waitingForInput in 0.2.2 — confirmed in 0.4.2 types
// actions: not on IStep in 0.4.2; actions arrive on ask steps over the socket
// elements: not on IStep in 0.4.2; arrive on assistant messages over the socket
// ---------------------------------------------------------------------------

interface IStepExtended extends IStep {
  waitForAnswer?: boolean;
  actions?: IAction[];
  elements?: AnyElement[];
}

// ---------------------------------------------------------------------------
// Internal message model
// ---------------------------------------------------------------------------

export type MessageKind =
  | "user"        // cl.Message from the user
  | "assistant"   // cl.Message from the assistant
  | "tool"        // cl.Step(type="tool") — status/progress step
  | "ask_action"  // cl.AskActionMessage — approve/reject buttons
  | "ask_form"    // cl.AskElementMessage — DynamicForm, PlanViewer etc.
  | "ask_plain";  // cl.AskUserMessage — plain text input ask

export interface FlatItem {
  step: IStepExtended;
  kind: MessageKind;
  actions: IAction[];
}

// ---------------------------------------------------------------------------
// Step classifiers
// ---------------------------------------------------------------------------

function classifyStep(step: IStepExtended): MessageKind {
  if (step.waitForAnswer) {
    if (step.actions?.length) return "ask_action";
    // Any wait-for-answer without actions is element-shaped (AskElementMessage
    // → DynamicForm/PlanViewer). step.type is unreliable here — AskElementMessage
    // arrives with wire type "assistant_message" in 0.4.x, not "tool".
    // If there's no element attached, ElementList renders nothing and the text
    // alone shows — same UX as a plain ask.
    return "ask_form";
  }
  if (step.type === "user_message") return "user";
  if (step.type === "assistant_message") return "assistant";
  if (step.type === "tool") return "tool";
  return "tool"; // fallback — never silently swallow
}

function isContainerStep(step: IStepExtended): boolean {
  return (
    step.type === "run" ||
    step.type === "embedding" ||
    step.type === "retrieval" ||
    step.type === "rerank" ||
    (step.type === "tool" && !step.name && !step.output && !step.waitForAnswer)
  );
}

// ---------------------------------------------------------------------------
// Tree flattener
// ---------------------------------------------------------------------------

export function flattenMessages(messages: IStep[]): FlatItem[] {
  return (messages as IStepExtended[]).flatMap(flattenStep);
}

function flattenStep(step: IStepExtended): FlatItem[] {
  const children: FlatItem[] = step.steps
    ? (step.steps as IStepExtended[]).flatMap(flattenStep)
    : [];
  if (isContainerStep(step)) return children;
  return [{ step, kind: classifyStep(step), actions: step.actions ?? [] }, ...children];
}

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

export const isUserMessage      = (item: FlatItem) => item.kind === "user";
export const isAssistantMessage = (item: FlatItem) => item.kind === "assistant";
export const isToolStep         = (item: FlatItem) => item.kind === "tool";
export const isAskAction        = (item: FlatItem) => item.kind === "ask_action";
export const isAskForm          = (item: FlatItem) => item.kind === "ask_form";
export const isAskPlain         = (item: FlatItem) => item.kind === "ask_plain";
export const isWaitingForInput  = (item: FlatItem) =>
  item.kind === "ask_action" || item.kind === "ask_form" || item.kind === "ask_plain";

// ---------------------------------------------------------------------------
// ─── TODO: Artifact viewers ──────────────────────────────────────────────────
//
// All arrive in step.elements[] and currently show NoViewerFallback.
// Register in VIEWER_REGISTRY (elements.ts) as each is built.
//
// Priority order:
//   1. FileDownloadElement  — cl.File; simple <a download> with mime badge
//   2. CollapsibleJsonElement — cl.CustomElement CollapsibleJson
//   3. IFCViewerElement     — cl.CustomElement IFCViewer (nearly ready)
//   4. ExodusViewerElement  — cl.CustomElement ExodusViewer
//   5. MermaidElement       — cl.CustomElement Mermaid
//   6. ThermalAnalysisElement — cl.CustomElement ThermalAnalysis (Plotly)
//
// NOTE: Audit plugins/ folder to confirm CustomElement names before building
//   IFC, Mermaid, and ThermalAnalysis viewers — names above are assumed.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: ask_plain ────────────────────────────────────────────────────────
//
// cl.AskUserMessage — not currently used in message_handler.py but part of
// the Chainlit API. Currently collapses into ask_form (text + empty
// ElementList = same UX as a plain ask). When a real text-input ask is
// needed, split the classifier and render an inline <input>+submit.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// Future extraction stubs — establish location before logic grows here
// ---------------------------------------------------------------------------

// TODO: extractArtifacts(messages: IStep[]): Artifact[]
// Scan flattened tree for assistant messages with file/pdf/custom elements.
// Feeds the Artifacts tab content and badge count.

// TODO: extractAgentIdentity(step: IStep): string | null
// Extract which agent produced a step from metadata or step.name patterns.
// Feeds per-agent attribution on messages and the Agents tab badge count.

// TODO: unreadCount(items: FlatItem[], lastSeenId: string | null): number
// Count assistant messages + tool completions after lastSeenId.
// Feeds the Chat tab processing indicator in ProjectView.
