// Phase B: role_taker carries the structured Attendee end-to-end so the
// backend route can render the (member)/(guest) badge from the DB-authoritative
// `member_id` instead of guessing against a static name list. Empty / unset
// roles are sent as `null` (matches the backend's `Optional[Attendee]`).
export type AgendaSnapshotRoleTaker = {
  id?: string;
  name: string;
  member_id: string;
} | null;

export type AgendaSnapshot = {
  meta: Record<string, unknown>;
  segments: Array<{
    id: string;
    type: string;
    start_time: string;
    duration: number;
    role_taker: AgendaSnapshotRoleTaker;
    buffer_before: number;
    // Phase 3: preserve segment-level detail across the agent round-trip.
    // Defaults to "" rather than undefined so the wire shape matches the
    // backend's `Segment` defaults — easier to compare / diff state.
    title: string;
    content: string;
    related_segment_ids: string;
  }>;
};

export type ToolCallStatus = 'pending' | 'ok' | 'retry';

// Ordered timeline element. The reducer pushes a new part when the SSE
// stream emits something new; same-kind chunks (text/text or
// thinking/thinking) coalesce into the trailing part. Tool parts hold
// only the toolCallId so `tool_call_end` can update the canonical entry
// in `ChatMessage.toolCalls` without disturbing render order.
export type MessagePart =
  | { kind: 'thinking'; content: string }
  | { kind: 'text'; content: string }
  | { kind: 'tool'; toolCallId: string };

export type RouterAgentKind = 'router' | 'meeting' | 'statistics';
export type RouterRouteKind =
  | 'specialist'
  | 'clarify'
  | 'refuse'
  | 'direct_answer';

export type RouterDecision = {
  route: RouterRouteKind;
  intent: string;
  reason: string;
  agent_kind?: RouterAgentKind | null;
  confidence?: number | null;
  clarification_question?: string | null;
  direct_response?: string | null;
  metadata?: Record<string, unknown>;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  toolCalls?: Array<{
    id: string;
    name: string;
    args: Record<string, unknown>;
    result?: unknown;
    status: ToolCallStatus;
  }>;
  // Linear timeline of streamed parts (text / thinking / tool refs) in
  // the order the model produced them. Renderer iterates this list so
  // text and tool calls interleave naturally instead of collapsing into
  // separate "all tools then all text" sections. `content`, `thinking`,
  // and `toolCalls` above remain the source of truth for empty-checks,
  // persistence, and tool status — `parts` is render-only positioning.
  parts?: MessagePart[];
  seq?: number;
  // Legacy: inline error on the bubble. Kept as a fallback for messages that
  // errored before we started routing errors to the top banner. New errors
  // use the top-of-panel banner instead.
  error?: string;
  // True when the user aborted the turn mid-stream via the Stop button.
  // Displayed as a small "[已取消]" footer.
  cancelled?: boolean;
  // Unified /agent/turn only: router decision emitted before specialist
  // events. Kept on the assistant bubble for lightweight route visibility.
  routerDecision?: RouterDecision;
  // Meeting turns can be reverted. Stats/router-only turns also carry seq
  // values, but those belong to other stores and must not show the revert UI.
  canRevert?: boolean;
};

export type AgentTurnEvent =
  | { type: 'router_decision'; data: { seq: number; decision: RouterDecision } }
  | { type: 'thinking'; data: { chunk: string } }
  | { type: 'assistant_text'; data: { chunk: string } }
  | {
      type: 'tool_call_start';
      data: { id: string; name: string; args: Record<string, unknown> };
    }
  | {
      type: 'tool_call_end';
      data: {
        id: string;
        status?: 'ok' | 'retry';
        result: unknown;
        agenda_after?: AgendaSnapshot;
      };
    }
  | {
      type: 'done';
      data: {
        seq: number;
        final_agenda?: AgendaSnapshot;
        final_text: string;
        router_only?: boolean;
      };
    }
  | {
      type: 'error';
      data: { reason: string; recoverable: boolean; message: string };
    }
  // Synthetic event emitted by useUnifiedAgentTurn when the user aborts.
  // Backend never sends this; it's a client-side signal so onEvent can
  // mark the bubble + reset loading state in the same update path.
  | { type: 'cancelled'; data: Record<string, never> };
