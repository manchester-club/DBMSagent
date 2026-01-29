import { useState, useEffect, useRef, useCallback } from 'react';
import { StreamEvent, Message, ToolCall } from '../types/agent';

export function useWebSocket(agentId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const currentToolCallRef = useRef<Map<string, ToolCall>>(new Map());
  const currentMessageRef = useRef<string>('');

  const connect = useCallback(() => {
    if (!agentId) {
      // 如果没有 agentId，不连接但也不报错
      setIsConnected(false);
      return;
    }

    // 如果已经有连接，先关闭
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {
        // 忽略关闭错误
      }
      wsRef.current = null;
    }

    try {
      console.log('正在连接 WebSocket...', 'ws://localhost:8000/ws/stream');
      const ws = new WebSocket('ws://localhost:8000/ws/stream');
      wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket 连接成功');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data: StreamEvent = JSON.parse(event.data);

      switch (data.type) {
        case 'dispatch':
          // DISPATCH 事件：调度信息
          setMessages((prev) => [
            ...prev,
            {
              id: `dispatch_${data.timestamp || Date.now()}`,
              type: 'dispatch',
              content: data.content || '',
              timestamp: data.timestamp || Date.now(),
              agent: data.agent,
              orchestrator: data.orchestrator,
            } as Message,
          ]);
          break;

        case 'think':
          // THINK 事件：Agent 思考
          setMessages((prev) => [
            ...prev,
            {
              id: `think_${data.timestamp || Date.now()}`,
              type: 'think',
              content: data.content || '',
              timestamp: data.timestamp || Date.now(),
              agent: data.agent,
            } as Message,
          ]);
          break;

        case 'tool':
          // TOOL 事件：工具调用
          const toolCallId = data.tool_id || `tool_${data.timestamp || Date.now()}`;
          
          setMessages((prev) => {
            // 查找是否已存在相同 tool_id 的消息（更新状态）
            const existingIndex = prev.findIndex(
              (msg) => msg.type === 'tool' && msg.toolCall && msg.id === toolCallId
            );
            
            const toolCall: ToolCall = {
              toolName: data.tool_name || 'unknown',
              args: data.args || {},
              expanded: false,
              result: data.result,
            };

            if (existingIndex >= 0) {
              // 更新现有消息（从 RUNNING 到 COMPLETED）
              const updated = [...prev];
              const existingToolCall = updated[existingIndex].toolCall;
              updated[existingIndex] = {
                ...updated[existingIndex],
                status: data.status,
                duration: data.duration,
                toolCall: {
                  ...existingToolCall,
                  toolName: data.tool_name || existingToolCall?.toolName || 'unknown',
                  args: existingToolCall?.args || data.args || {},
                  result: data.result || existingToolCall?.result,
                },
              } as Message;
              return updated;
            } else {
              // 创建新消息
              return [
                ...prev,
                {
                  id: toolCallId,
                  type: 'tool',
                  content: data.tool_name || 'tool',
                  timestamp: data.timestamp || Date.now(),
                  agent: data.agent,
                  status: data.status,
                  duration: data.duration,
                  toolCall,
                } as Message,
              ];
            }
          });
          break;

        case 'text_chunk':
          // 累积文本块（保留兼容性）
          currentMessageRef.current += data.content || '';
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.type === 'assistant' && !lastMsg.toolCall) {
              return [
                ...prev.slice(0, -1),
                {
                  ...lastMsg,
                  content: currentMessageRef.current,
                },
              ];
            } else {
              const newMsg: Message = {
                id: Date.now().toString(),
                type: 'assistant',
                content: currentMessageRef.current,
                timestamp: Date.now(),
              };
              return [...prev, newMsg];
            }
          });
          break;

        case 'tool_call_start':
          // 开始工具调用（保留兼容性）
          const toolCallId2 = `${data.tool_name}_${Date.now()}`;
          const toolCall2: ToolCall = {
            toolName: data.tool_name || 'unknown',
            args: data.args || {},
            expanded: false,
          };
          currentToolCallRef.current.set(toolCallId2, toolCall2);

          setMessages((prev) => {
            const toolMsg: Message = {
              id: toolCallId2,
              type: 'tool',
              content: `调用工具: ${data.tool_name}`,
              timestamp: Date.now(),
              toolCall: toolCall2,
              status: 'RUNNING',
            };
            return [...prev, toolMsg];
          });
          break;

        case 'tool_call_result':
          // 工具执行结果（保留兼容性）
          setMessages((prev) => {
            return prev.map((msg) => {
              if (msg.type === 'tool' && msg.toolCall && msg.toolCall.toolName === data.tool_name) {
                return {
                  ...msg,
                  toolCall: {
                    ...msg.toolCall,
                    result: data.result,
                  },
                  status: 'COMPLETED',
                } as Message;
              }
              return msg;
            });
          });
          break;

        case 'done':
          setIsStreaming(false);
          currentMessageRef.current = '';
          currentToolCallRef.current.clear();
          break;

        case 'error':
          setIsStreaming(false);
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now().toString(),
              type: 'assistant',
              content: `错误: ${data.message}`,
              timestamp: Date.now(),
            },
          ]);
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
      setIsStreaming(false);
      // 尝试重新连接（延迟 3 秒）
      if (agentId) {
        setTimeout(() => {
          if (agentId && (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED)) {
            console.log('尝试重新连接 WebSocket...');
            connect();
          }
        }, 3000);
      }
    };

    ws.onclose = (event) => {
      console.log('WebSocket 连接关闭', event.code, event.reason);
      setIsConnected(false);
      setIsStreaming(false);
      // 如果连接关闭且 agentId 仍然存在，尝试重连
      if (agentId) {
        setTimeout(() => {
          if (agentId && (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED)) {
            console.log('尝试重新连接 WebSocket...');
            connect();
          }
        }, 3000); // 增加重连延迟，避免频繁重连
      }
    };
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      setIsConnected(false);
      setIsStreaming(false);
    }
  }, [agentId]);

  const sendMessage = useCallback(
    (message: string) => {
      // 如果连接未打开，尝试连接
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        if (agentId) {
          connect();
          // 等待连接建立后再发送
          setTimeout(() => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              sendMessage(message);
            }
          }, 500);
        }
        return;
      }

      if (!agentId) {
        return;
      }

      // 添加用户消息
      const userMsg: Message = {
        id: Date.now().toString(),
        type: 'user',
        content: message,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // 重置状态
      currentMessageRef.current = '';
      setIsStreaming(true);

      // 发送消息到服务器
      try {
        wsRef.current.send(
          JSON.stringify({
            agent_id: agentId,
            message: message,
          })
        );
      } catch (error) {
        console.error('发送消息失败:', error);
        setIsStreaming(false);
      }
    },
    [agentId, connect]
  );

  const toggleToolCall = useCallback((messageId: string) => {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id === messageId && msg.toolCall) {
          return {
            ...msg,
            toolCall: {
              ...msg.toolCall,
              expanded: !msg.toolCall.expanded,
            },
          };
        }
        return msg;
      })
    );
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    currentMessageRef.current = '';
    currentToolCallRef.current.clear();
  }, []);

  useEffect(() => {
    if (agentId) {
      connect();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [agentId, connect]);

  return {
    messages,
    isConnected,
    isStreaming,
    sendMessage,
    toggleToolCall,
    clearMessages,
  };
}
