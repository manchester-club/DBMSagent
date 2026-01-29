import { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Space, Empty, Spin } from 'antd';
import { SendOutlined, ClearOutlined, DownloadOutlined } from '@ant-design/icons';
import { MessageBubble } from './MessageBubble';
import { useWebSocket } from '../hooks/useWebSocket';

interface ChatWindowProps {
  agentId: string | null;
}

export function ChatWindow({ agentId }: ChatWindowProps) {
  const [input, setInput] = useState('');
  const { messages, isConnected, isStreaming, sendMessage, toggleToolCall, clearMessages } =
    useWebSocket(agentId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || !agentId || !isConnected) return;
    sendMessage(input);
    setInput('');
  };

  const handleExport = () => {
    const content = messages
      .map((msg) => {
        const time = new Date(msg.timestamp).toLocaleString('zh-CN');
        const role = msg.type === 'user' ? '用户' : msg.type === 'tool' ? '工具' : '助手';
        let text = `[${time}] ${role}: ${msg.content}`;
        if (msg.toolCall) {
          text += `\n工具: ${msg.toolCall.toolName}`;
          text += `\n参数: ${JSON.stringify(msg.toolCall.args, null, 2)}`;
          if (msg.toolCall.result) {
            text += `\n结果: ${msg.toolCall.result}`;
          }
        }
        return text;
      })
      .join('\n\n');

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `对话记录_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!agentId) {
    return (
      <Card>
        <Empty description="请先选择一个智能体" />
      </Card>
    );
  }

  return (
    <Card
      title="对话"
      extra={
        <Space>
          <Button
            icon={<ClearOutlined />}
            onClick={clearMessages}
            disabled={messages.length === 0}
          >
            清空
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            disabled={messages.length === 0}
          >
            导出
          </Button>
        </Space>
      }
      style={{ height: 'calc(100vh - 300px)', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 0',
          marginBottom: 16,
        }}
      >
        {messages.length === 0 ? (
          <Empty description="开始对话吧" />
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onToggleToolCall={toggleToolCall}
            />
          ))
        )}
        {isStreaming && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Spin size="small" /> <span style={{ marginLeft: 8 }}>思考中...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={isConnected ? '输入消息...' : '连接中...'}
          disabled={!isConnected || isStreaming}
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!isConnected || isStreaming || !input.trim()}
        >
          发送
        </Button>
      </Space.Compact>
    </Card>
  );
}
