/**
 * src/lib/chainlit.ts
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
 *
 * Not yet implemented — see TODOs below:
 *   ✗ ask_form  (AskElementMessage — DynamicForm, PlanViewer)
 *   ✗ ask_plain (AskUserMessage)
 *   ✗ all element types on assistant messages (Pdf, File, Image, CustomElement)
 *   ✗ all artifact viewer plugins (IFC, mermaid, SVG, image, thermal)
 *   ✗ artifact fallback renderers (CollapsibleJson, file download, reference)
 *   ✗ file upload UI (multi-file, CAD, PDF preview)
 *   ✗ FollowUpSuggestions chips
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { IStep, IAction } from "@chainlit/react-client";

// ---------------------------------------------------------------------------
// IStep extension
//
// @chainlit/react-client 0.4.2 types IStep with most fields but omits some
// that arrive over the wire from Chainlit 2.x backends. We extend locally
// rather than casting to any throughout the codebase.
//
// waitForAnswer: renamed from waitingForInput in 0.2.2 — confirmed in 0.4.2 types
// actions: not on IStep in 0.4.2; actions arrive on ask steps over the socket
// ---------------------------------------------------------------------------

interface IStepExtended extends IStep {
  waitForAnswer?: boolean;
  actions?: IAction[];
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
    if (step.type === "tool") return "ask_form";
    return "ask_plain";
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
// ─── TODO: Interactive ask flows ────────────────────────────────────────────
//
// ASK_FORM — cl.AskElementMessage
//   Backend: message_handler.py → _handle_needs_info()
//            cl.AskElementMessage(content=..., element=cl.CustomElement(name="DynamicForm", props={
//              title, fields:[{id,label,input_type,required,options?,default?,help?}],
//              submitLabel, formId
//            }))
//   Wire format: step.waitForAnswer=true, step.type="tool", step.element present
//   Detection: check step.element?.name === "DynamicForm" (or "PlanViewer")
//   Render: <DynamicForm /> matching field schema — text, select, multi-select inputs
//   Submit: sendMessage({ output: JSON.stringify(answers), type: "user_message" })
//           must include formId in payload so backend correlates the submission
//   Also used for: PlanViewer (plan_ready flow) — see plan section below
//   Blocked on: classifyElement() implementation + CustomElement registry
//
// ASK_PLAIN — cl.AskUserMessage
//   Backend: not currently used in message_handler.py but part of Chainlit API
//   Wire format: step.waitForAnswer=true, step.type="user_message" variant
//   Render: inline text input beneath the ask message, submit via sendMessage
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: Plan approval flow ────────────────────────────────────────────────
//
// Backend: message_handler.py → _handle_plan_ready()
//   Step 1 — PlanViewer display:
//     cl.Message(content=..., elements=[cl.CustomElement(name="PlanViewer", props={
//       plan: { steps: [...] }, stepStatuses: {}
//     })])
//     → lands as assistant message with elements[]. Needs classifyElement to
//       route to <PlanViewer /> instead of being silently dropped.
//
//   Step 2 — AskActionMessage approve/reject:
//     cl.AskActionMessage(content=..., actions=[
//       cl.Action(name="approve", label="Approve & Execute"),
//       cl.Action(name="reject",  label="Reject")
//     ])
//     → already handled by ask_action kind + ActionButtons component ✓
//
//   Step 3 — execution status steps stream in while plan runs:
//     cl.Step(name="Executing plan...", type="tool") with status updates
//     → already handled by tool kind + ToolStep component ✓
//
// Render needed: <PlanViewer plan={...} stepStatuses={...} /> — shows ordered
//   steps with running/completed/failed status indicators. stepStatuses updates
//   as tool steps stream in (requires lifting state or a context).
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: Element rendering on assistant messages ───────────────────────────
//
// Currently step.elements[] is completely ignored in Chat.tsx. All of the
// below land in elements[] on assistant messages and need to be rendered.
//
// KNOWN ELEMENT TYPES (from backend message_handler.py → _handle_final_response,
//   render_artifacts, and cl.Message calls throughout):
//
// cl.Pdf(name, path, display="inline")
//   → render as inline PDF viewer (browser native <embed> or iframe)
//   → backend produces these for PDF artifacts and PDF uploads
//
// cl.File(name, path, display="inline", mime)
//   → render as a download link with filename + mime badge
//   → backend produces for: CAD files (.stp/.step), zip, generic binaries
//   → CAD MIME types: model/step, application/step, application/x-step etc.
//     (see CAD_FILE_MIMETYPES in message_handler.py)
//
// cl.CustomElement(name="CollapsibleJson", props={data, name, description, json_type})
//   → expandable/collapsible JSON tree viewer
//   → backend produces for JSON artifacts and data responses
//
// cl.CustomElement(name="FollowUpSuggestions", props={suggestions:string[], title})
//   → row of clickable suggestion chips below assistant message
//   → clicking a chip should call handleSend(suggestion)
//   → backend produces from metadata.follow_up_suggestions in final response
//
// cl.CustomElement(name="PlanViewer", props={plan, stepStatuses})
//   → see plan approval flow above
//
// cl.CustomElement(name="DynamicForm", props={...})
//   → only appears inside AskElementMessage, not as a standalone element
//
// ELEMENT CLASSIFICATION FUNCTION NEEDED:
//   classifyElement(element: IElement): ElementKind
//   where ElementKind = "pdf" | "file" | "image" | "json" | "suggestions"
//                     | "plan_viewer" | "dynamic_form" | "plugin" | "unknown"
//   This gates all element rendering — nothing shows until this exists.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: Plugin-rendered artifact viewers ──────────────────────────────────
//
// Backend: render_artifacts() calls _plugins.render_artifact(artifact) first.
// If the plugin system handles it, it returns a cl.CustomElement or cl.Image.
// On the frontend, these arrive as elements on assistant messages.
//
// Existing plugins (from prior architecture discussions — each has a JSX wrapper
// that needs minor tweaks to work in the new frontend):
//
// IFC viewer — cl.CustomElement(name="IFCViewer"?) or similar
//   Plugin: plugins/ifc/
//   Library: @thatopen/components or Three.js based
//   Input: artifact with mime model/step or IFC file URI
//   Work: verify CustomElement name matches, fix props destructuring issue noted
//         in prior audit, confirm @thatopen packages resolve in Vite build
//
// Mermaid diagrams — cl.CustomElement(name="Mermaid"?) or cl.Text with mermaid syntax
//   Plugin: plugins/mermaid/
//   Library: mermaid.js
//   Input: artifact with mermaid diagram source or mime text/x-mermaid
//   Work: confirm element name/type, ensure mermaid.initialize() called once
//
// SVG viewer — cl.CustomElement or cl.Image with SVG content
//   Plugin: plugins/svg/
//   Input: artifact with mime image/svg+xml
//   Work: likely just inline <img> or dangerouslySetInnerHTML — verify sanitization
//
// Image viewer — cl.Image(name, url/path, display)
//   Plugin: plugins/image/
//   Input: standard image mimes (image/png, image/jpeg etc.)
//   Work: probably simplest migration — render as <img> with lightbox
//
// Thermal analysis — cl.CustomElement(name="ThermalAnalysis"?) with Plotly data
//   Plugin: plugins/thermal_analysis/
//   Library: react-plotly.js (this is the Plotly Dash retirement target)
//   Input: artifact with Plotly figure JSON
//   Work: wire to universal Plotly component once that is built (Task 6)
//         in the meantime can fall through to CollapsibleJson
//
// NOTE: Plugin CustomElement names need to be confirmed against actual plugin
// source — the names above are assumed. Audit plugins/ folder before building
// the element registry.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: Artifact fallback renderers ───────────────────────────────────────
//
// Backend: render_artifacts() fallback path (after plugin misses) produces:
//
// "pdf" type → cl.Pdf — covered above
//
// "data" type (mime application/json or text/csv) → cl.CustomElement CollapsibleJson
//   or cl.File if json_body unavailable — covered above
//
// "report" type (mime text/markdown or text/plain) → text appended to message content
//   → already renders if it lands in step.output ✓
//   → if it lands as cl.Text element, need to handle cl.Text element type
//
// "file" type (octet-stream, zip, gzip, CAD) → cl.File download — covered above
//
// "reference" type → formatted citation text appended to message content
//   → already renders if in step.output ✓
//
// "unknown" type → cl.File fallback + label text
//   → covered by cl.File handler above
//
// Text parts from render_artifacts are appended to response.report/response_text
// and arrive in step.output — these render already via markdown. Only the
// element-based renderers (Pdf, File, CustomElement) are the gap.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// ─── TODO: File upload UI ────────────────────────────────────────────────────
//
// Backend: message_handler.py handles message.elements (uploaded files)
//   before the A2A call. The frontend needs to support sending them.
//
// Requirements:
//   Attach button in chat input bar → opens file picker
//   Multi-file support (message.elements is a list)
//   20 MB per-file limit (MAX_UPLOAD_BYTES in backend) — show error if exceeded
//   CAD file types must be accepted: .stp, .step (not in browser default lists)
//   PDF files: backend renders inline via cl.Pdf — upload flow should reflect this
//   All other files: passed to agent via uploaded_files payload
//
// Chainlit upload mechanism: sendMessage() accepts an attachments[] param
//   (second arg) — this is currently passed as [] everywhere. Needs to be
//   wired to actual File objects from the file picker.
//   Confirm attachment shape expected by @chainlit/react-client 0.4.2.
// ────────────────────────────────────────────────────────────────────────────

// ---------------------------------------------------------------------------
// Future extraction stubs — establish location before logic grows here
// ---------------------------------------------------------------------------

// TODO: classifyElement(element: IElement): ElementKind
// Gates all element rendering. Implement after confirming CustomElement names
// from actual plugin source code audit.

// TODO: extractArtifacts(messages: IStep[]): Artifact[]
// Scan flattened tree for assistant messages with file/pdf/custom elements.
// Feeds the Artifacts tab content and badge count.

// TODO: extractAgentIdentity(step: IStep): string | null
// Extract which agent produced a step from metadata or step.name patterns.
// Feeds per-agent attribution on messages and the Agents tab badge count.

// TODO: unreadCount(items: FlatItem[], lastSeenId: string | null): number
// Count assistant messages + tool completions after lastSeenId.
// Feeds the Chat tab processing indicator in ProjectView.
