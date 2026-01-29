import { useState } from 'react';
import { Input, Button, Space } from 'antd';
import { SendOutlined, ClearOutlined, DownloadOutlined } from '@ant-design/icons';

interface InputPanelProps {
  onSend: (message: string) => void;
  onClear: () => void;
  onExport: () => void;
  isConnected: boolean;
  isStreaming: boolean;
  hasMessages: boolean;
}

export function InputPanel({ 
  onSend, 
  onClear, 
  onExport, 
  isConnected, 
  isStreaming,
  hasMessages,
}: InputPanelProps) {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim() || !isConnected) return;
    onSend(input);
    setInput('');
  };

  return (
    <div style={{
      padding: '16px 20px',
      backgroundColor: '#0a0e27',
      borderTop: '1px solid #1a1f3a',
    }}>
      {!isConnected && (
        <div style={{
          marginBottom: 12,
          padding: '8px 12px',
          backgroundColor: '#1a1f3a',
          borderRadius: 4,
          border: '1px solid #faad14',
          color: '#faad14',
          fontSize: 12,
        }}>
          ⚠️ 后端服务未连接（WebSocket: ws://localhost:8000/ws/stream）。请确保后端服务正在运行。
        </div>
      )}
      <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={isConnected ? '输入消息...' : '后端服务未连接，无法发送消息'}
          disabled={!isConnected || isStreaming}
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ 
            flex: 1,
            backgroundColor: '#141829',
            borderColor: '#1a1f3a',
            color: '#e8e8e8',
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!isConnected || isStreaming || !input.trim()}
          style={{
            backgroundColor: '#1890ff',
            borderColor: '#1890ff',
          }}
        >
          发送
        </Button>
      </Space.Compact>
      
      <Space>
        <Button
          icon={<ClearOutlined />}
          onClick={onClear}
          disabled={!hasMessages}
          style={{
            backgroundColor: 'transparent',
            borderColor: '#1a1f3a',
            color: '#e8e8e8',
          }}
        >
          清空
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={onExport}
          disabled={!hasMessages}
          style={{
            backgroundColor: 'transparent',
            borderColor: '#1a1f3a',
            color: '#e8e8e8',
          }}
        >
          导出
        </Button>
      </Space>
    </div>
  );
}
