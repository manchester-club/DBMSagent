import { Message } from '../types/agent';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.type === 'user';
  const isAssistant = message.type === 'assistant' || message.type === 'think';
  const isDispatch = message.type === 'dispatch';
  const isTool = message.type === 'tool';
  const hasToolCall = message.toolCall !== undefined;

  if (isUser) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: 20,
          animation: 'fadeIn 0.3s ease-in',
        }}
      >
        <div
          style={{
            maxWidth: '70%',
            padding: '12px 16px',
            borderRadius: 8,
            backgroundColor: '#1890ff',
            color: '#fff',
            wordWrap: 'break-word',
          }}
        >
          <div style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  if (isDispatch) {
    return (
      <div
        style={{
          marginBottom: 20,
          animation: 'fadeIn 0.3s ease-in',
        }}
      >
        <div
          style={{
            backgroundColor: '#1a2332',
            borderLeft: '3px solid #1890ff',
            padding: '12px 16px',
            borderRadius: 4,
          }}
        >
          <div
            style={{
              color: '#1890ff',
              fontWeight: 600,
              fontSize: 13,
              marginBottom: 4,
            }}
          >
            派发 → {message.agent || 'Agent'}
          </div>
          {message.content && (
            <div
              style={{
                color: '#e8e8e8',
                fontSize: 12,
                marginTop: 4,
              }}
            >
              {message.content}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isTool && message.toolCall) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-start',
          marginBottom: 20,
          animation: 'fadeIn 0.3s ease-in',
        }}
      >
        <div
          style={{
            maxWidth: '70%',
            padding: '12px 16px',
            borderRadius: 8,
            backgroundColor: '#141829',
            border: '1px solid #1a1f3a',
            color: '#e8e8e8',
            wordWrap: 'break-word',
          }}
        >
          <div
            style={{
              color: '#faad14',
              fontWeight: 600,
              fontSize: 13,
              marginBottom: 8,
            }}
          >
            执行工具调用：{message.toolCall.toolName}
          </div>
          <div
            style={{
              marginTop: 8,
              backgroundColor: '#0a0e27',
              border: '1px solid #1a1f3a',
              borderRadius: 6,
              padding: 12,
            }}
          >
            {message.toolCall.args && Object.keys(message.toolCall.args).length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      marginBottom: 4,
                    }}
                  >
                    参数：
                  </div>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      margin: '4px 0',
                      padding: '8px',
                      backgroundColor: '#0a0e27',
                      borderRadius: 4,
                      overflowX: 'auto',
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {JSON.stringify(message.toolCall.args, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {message.toolCall.result && (
                <div>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      marginBottom: 4,
                    }}
                  >
                    返回：
                  </div>
                  <div
                    style={{
                      color: '#52c41a',
                      fontSize: 12,
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      marginTop: 8,
                      padding: '8px',
                      backgroundColor: '#0a0e27',
                      borderRadius: 4,
                      maxHeight: '400px',
                      overflowY: 'auto',
                      overflowX: 'auto',
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {typeof message.toolCall.result === 'string'
                        ? message.toolCall.result
                        : JSON.stringify(message.toolCall.result, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
          </div>
        </div>
      </div>
    );
  }

  if (isAssistant) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-start',
          marginBottom: 20,
          animation: 'fadeIn 0.3s ease-in',
        }}
      >
        <div
          style={{
            maxWidth: '70%',
            padding: '12px 16px',
            borderRadius: 8,
            backgroundColor: '#141829',
            border: '1px solid #1a1f3a',
            color: '#e8e8e8',
            wordWrap: 'break-word',
          }}
        >
          {message.content && (
            <div
              style={{
                fontSize: 14,
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                marginBottom: hasToolCall ? 8 : 0,
              }}
            >
              {message.content}
            </div>
          )}

          {hasToolCall && message.toolCall && (
            <div
              style={{
                marginTop: 8,
                backgroundColor: '#0a0e27',
                border: '1px solid #1a1f3a',
                borderRadius: 6,
                padding: 12,
              }}
            >
              <div
                style={{
                  color: '#faad14',
                  fontWeight: 600,
                  fontSize: 13,
                  marginBottom: 8,
                }}
              >
                {message.toolCall.toolName}
              </div>

              {message.toolCall.args && Object.keys(message.toolCall.args).length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      marginBottom: 4,
                    }}
                  >
                    参数：
                  </div>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      margin: '4px 0',
                      padding: '8px',
                      backgroundColor: '#0a0e27',
                      borderRadius: 4,
                      overflowX: 'auto',
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {JSON.stringify(message.toolCall.args, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {message.toolCall.result && (
                <div>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 12,
                      marginBottom: 4,
                    }}
                  >
                    返回：
                  </div>
                  <div
                    style={{
                      color: '#52c41a',
                      fontSize: 12,
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      marginTop: 8,
                      padding: '8px',
                      backgroundColor: '#0a0e27',
                      borderRadius: 4,
                      maxHeight: '400px',
                      overflowY: 'auto',
                      overflowX: 'auto',
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {typeof message.toolCall.result === 'string'
                        ? message.toolCall.result
                        : JSON.stringify(message.toolCall.result, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}
