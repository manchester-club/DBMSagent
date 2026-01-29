import { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';
import { Message } from '../types/agent';

interface ActivityLogProps {
  messages: Message[];
  isStreaming: boolean;
  onToggleToolCall?: (messageId: string) => void;
}

export function ActivityLog({ messages, isStreaming }: ActivityLogProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#0a0e27',
        color: '#e8e8e8',
        borderRight: '1px solid #1a1f3a',
        height: '100%', // 确保占满父容器高度
        minHeight: 0, // 重要：允许 flex 子元素缩小
        overflow: 'hidden', // 防止内容溢出父容器
      }}
    >
      {/* Messages Container */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto', // 允许垂直滚动
          overflowX: 'hidden', // 防止水平滚动
          padding: '20px',
          backgroundColor: '#0a0e27',
          minHeight: 0, // 重要：允许 flex 子元素缩小
        }}
      >
        {messages.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              color: '#8c8c8c',
              padding: '40px 20px',
            }}
          >
            暂无消息
          </div>
        ) : (
          messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))
        )}
        {isStreaming && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-start',
              marginBottom: 20,
            }}
          >
            <div
              style={{
                maxWidth: '70%',
                padding: '12px 16px',
                borderRadius: 8,
                backgroundColor: '#141829',
                border: '1px solid #1a1f3a',
                color: '#8c8c8c',
                fontSize: 14,
                fontStyle: 'italic',
              }}
            >
              正在处理...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
