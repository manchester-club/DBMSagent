import { Card, Tag, Typography } from 'antd';
import { Message } from '../types/agent';
import { ToolCallCard } from './ToolCallCard';
// 简单的日期格式化函数
const formatTime = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const { Text } = Typography;

interface MessageBubbleProps {
  message: Message;
  onToggleToolCall: (messageId: string) => void;
}

export function MessageBubble({ message, onToggleToolCall }: MessageBubbleProps) {
  const isUser = message.type === 'user';
  const isTool = message.type === 'tool';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
      }}
    >
      <Card
        size="small"
        style={{
          maxWidth: '80%',
          backgroundColor: isUser ? '#1890ff' : isTool ? '#f0f0f0' : '#fff',
          borderColor: isUser ? '#1890ff' : '#d9d9d9',
        }}
        bodyStyle={{
          color: isUser ? '#fff' : '#000',
          padding: '12px 16px',
        }}
      >
        <div style={{ marginBottom: 8 }}>
          <Tag color={isUser ? 'blue' : isTool ? 'orange' : 'green'}>
            {isUser ? '用户' : isTool ? '工具' : '助手'}
          </Tag>
          <Text
            type="secondary"
            style={{
              fontSize: 12,
              color: isUser ? 'rgba(255,255,255,0.7)' : undefined,
              marginLeft: 8,
            }}
          >
            {formatTime(message.timestamp)}
          </Text>
        </div>
        {isTool && message.toolCall ? (
          <ToolCallCard
            toolCall={message.toolCall}
            onToggle={() => onToggleToolCall(message.id)}
          />
        ) : (
          <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {message.content}
          </div>
        )}
      </Card>
    </div>
  );
}
