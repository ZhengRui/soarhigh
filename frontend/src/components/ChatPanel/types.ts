export type AgendaSnapshot = {
  meta: Record<string, unknown>;
  segments: Array<{
    id: string;
    type: string;
    start_time: string;
    duration: number;
    role_taker: string;
    buffer_before: number;
  }>;
};

export type ToolCallStatus = 'pending' | 'ok' | 'retry';

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
  seq?: number;
  error?: string;
};

export type AgentTurnEvent =
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
        agenda_after: AgendaSnapshot;
      };
    }
  | {
      type: 'done';
      data: { seq: number; final_agenda: AgendaSnapshot; final_text: string };
    }
  | {
      type: 'error';
      data: { reason: string; recoverable: boolean; message: string };
    };
