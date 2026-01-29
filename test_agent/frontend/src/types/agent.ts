export interface Agent {
  id: string;
  name: string;
  description: string;
  tools: string[];
}

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'tool' | 'dispatch' | 'think';
  content: string;
  timestamp: number;
  toolCall?: ToolCall;
  agent?: string;
  orchestrator?: string;
  status?: 'RUNNING' | 'COMPLETED';
  duration?: string;
}

export interface ToolCall {
  toolName: string;
  args: Record<string, any>;
  result?: string;
  expanded?: boolean;
}

export interface StreamEvent {
  type: 'text_chunk' | 'tool_call_start' | 'tool_call_result' | 'done' | 'error' | 'dispatch' | 'think' | 'tool';
  content?: string;
  tool_name?: string;
  tool_id?: string;
  args?: Record<string, any>;
  result?: string;
  message?: string;
  timestamp?: number;
  agent?: string;
  orchestrator?: string;
  status?: 'RUNNING' | 'COMPLETED';
  duration?: string;
}
