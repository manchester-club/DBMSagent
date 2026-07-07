import { useState, useEffect } from 'react';
import { Layout, Spin } from 'antd';
import axios from 'axios';
import { AgentSelector } from './components/AgentSelector';
import { ActivityLog } from './components/ActivityLog';
import { Sidebar } from './components/Sidebar';
import { InputPanel } from './components/InputPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { Agent } from './types/agent';

const { Content } = Layout;

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  
  const { messages, isConnected, isStreaming, sendMessage, toggleToolCall, clearMessages } =
    useWebSocket(selectedAgent);

  useEffect(() => {
    loadAgents();
  }, []);

  // 添加错误边界和调试信息
  useEffect(() => {
    console.log('App mounted, loading:', loading, 'agents:', agents.length);
  }, [loading, agents]);

  const loadAgents = async () => {
    // 设置超时，确保即使后端未启动也能显示界面
    const timeoutId = setTimeout(() => {
      console.log('加载智能体超时，使用空列表');
      setAgents([]);
      setLoading(false);
    }, 2000);

    try {
      const response = await axios.get<Agent[]>('http://localhost:8000/api/agents', {
        timeout: 1500,
      });
      clearTimeout(timeoutId);
      setAgents(response.data);
      if (response.data.length > 0) {
        // 自动选择第一个 agent，这样 WebSocket 才能连接
        setSelectedAgent(response.data[0].id);
        console.log('已自动选择 Agent:', response.data[0].id);
      } else {
        console.warn('没有可用的 Agent');
      }
      setLoading(false);
    } catch (error: any) {
      clearTimeout(timeoutId);
      console.error('加载智能体失败:', error);
      // 即使后端未启动，也显示界面（使用空列表）
      setAgents([]);
      setLoading(false);
    }
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

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column',
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        backgroundColor: '#0a0e27',
        color: '#e8e8e8',
      }}>
        <Spin size="large" tip="加载中..." />
        <div style={{ marginTop: 20, color: '#8c8c8c', fontSize: 12 }}>
          正在连接后端服务...
        </div>
      </div>
    );
  }

  return (
    <Layout style={{ 
      minHeight: '100vh', 
      backgroundColor: '#0a0e27',
      color: '#e8e8e8',
    }}>
      <Content style={{ 
        display: 'flex', 
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
      }}>
        {/* Header with Agent Selector */}
        <AgentSelector
          agents={agents}
          selectedAgent={selectedAgent}
          onSelect={setSelectedAgent}
        />

        {/* Main Content Area */}
        <div style={{ 
          flex: 1, 
          display: 'flex', 
          overflow: 'hidden',
          minHeight: 0, // 重要：确保 flex 子元素可以缩小
        }}>
          {/* Left Panel - Activity Log */}
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0, // 重要：确保可以缩小
            overflow: 'hidden', // 防止内容溢出
          }}>
            <ActivityLog
              messages={messages}
              isStreaming={isStreaming}
              onToggleToolCall={toggleToolCall}
            />
          </div>

          {/* Right Panel - Sidebar (固定) */}
          <div style={{
            width: 320,
            flexShrink: 0, // 防止被压缩
            display: 'flex',
            flexDirection: 'column',
            height: '100%', // 固定高度
            overflow: 'hidden', // 防止内容溢出
          }}>
            <Sidebar messages={messages} />
          </div>
        </div>

        {/* Bottom Input Panel */}
        <InputPanel
          onSend={sendMessage}
          onClear={clearMessages}
          onExport={handleExport}
          isConnected={isConnected}
          isStreaming={isStreaming}
          hasMessages={messages.length > 0}
        />
      </Content>
    </Layout>
  );
}

export default App;
