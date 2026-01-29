import { Progress } from 'antd';
import { ReloadOutlined, ThunderboltOutlined, FileTextOutlined, StarOutlined, SafetyOutlined } from '@ant-design/icons';
import { Message } from '../types/agent';

interface ProgressPanelProps {
  messages: Message[];
  isStreaming: boolean;
}

export function ProgressPanel({ messages, isStreaming }: ProgressPanelProps) {
  // 计算指标
  const toolCalls = messages.filter(m => m.type === 'tool' || m.toolCall).length;
  const iterations = Math.ceil(messages.length / 2); // 粗略估算
  const tokens = Math.floor(messages.reduce((sum, m) => sum + m.content.length, 0) / 4); // 粗略估算
  
  // 计算进度（基于消息数量）
  const progress = messages.length > 0 ? Math.min((messages.length / 20) * 100, 100) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Progress */}
      <div style={{
        backgroundColor: '#141829',
        borderRadius: 8,
        padding: 16,
        border: '1px solid #1a1f3a',
      }}>
        <h4 style={{ margin: '0 0 12px 0', color: '#e8e8e8', fontSize: 14, fontWeight: 600 }}>PROGRESS</h4>
        <Progress
          percent={Math.round(progress)}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
          showInfo={true}
          format={(percent) => `${percent}%`}
        />
        <div style={{ 
          marginTop: 8, 
          color: '#8c8c8c', 
          fontSize: 12,
        }}>
          Messages processed {messages.length}
        </div>
      </div>

      {/* Metrics */}
      <div style={{
        backgroundColor: '#141829',
        borderRadius: 8,
        padding: 16,
        border: '1px solid #1a1f3a',
      }}>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
        }}>
          <div style={{
            padding: 12,
            backgroundColor: '#0a0e27',
            borderRadius: 6,
            border: '1px solid #1a1f3a',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <ReloadOutlined style={{ color: '#1890ff' }} />
              <span style={{ color: '#8c8c8c', fontSize: 11 }}>ITERATIONS</span>
            </div>
            <div style={{ color: '#e8e8e8', fontSize: 20, fontWeight: 600 }}>
              {iterations}
            </div>
          </div>

          <div style={{
            padding: 12,
            backgroundColor: '#0a0e27',
            borderRadius: 6,
            border: '1px solid #1a1f3a',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <ThunderboltOutlined style={{ color: '#faad14' }} />
              <span style={{ color: '#8c8c8c', fontSize: 11 }}>TOOL CALLS</span>
            </div>
            <div style={{ color: '#e8e8e8', fontSize: 20, fontWeight: 600 }}>
              {toolCalls}
            </div>
          </div>

          <div style={{
            padding: 12,
            backgroundColor: '#0a0e27',
            borderRadius: 6,
            border: '1px solid #1a1f3a',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <FileTextOutlined style={{ color: '#52c41a' }} />
              <span style={{ color: '#8c8c8c', fontSize: 11 }}>TOKENS</span>
            </div>
            <div style={{ color: '#e8e8e8', fontSize: 20, fontWeight: 600 }}>
              {tokens > 1000 ? `${(tokens / 1000).toFixed(1)}K` : tokens}
            </div>
          </div>

          <div style={{
            padding: 12,
            backgroundColor: '#0a0e27',
            borderRadius: 6,
            border: '1px solid #1a1f3a',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <StarOutlined style={{ color: '#eb2f96' }} />
              <span style={{ color: '#8c8c8c', fontSize: 11 }}>FINDINGS</span>
            </div>
            <div style={{ color: '#e8e8e8', fontSize: 20, fontWeight: 600 }}>
              {toolCalls}
            </div>
          </div>
        </div>
      </div>

      {/* Status Score */}
      <div style={{
        backgroundColor: '#141829',
        borderRadius: 8,
        padding: 16,
        border: '1px solid #1a1f3a',
        textAlign: 'center',
      }}>
        <h4 style={{ margin: '0 0 12px 0', color: '#e8e8e8', fontSize: 14, fontWeight: 600 }}>STATUS</h4>
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <Progress
            type="circle"
            percent={isStreaming ? 50 : 100}
            strokeColor={isStreaming ? '#faad14' : '#52c41a'}
            format={() => (
              <div style={{ textAlign: 'center' }}>
                <SafetyOutlined style={{ fontSize: 24, color: isStreaming ? '#faad14' : '#52c41a' }} />
                <div style={{ color: '#e8e8e8', fontSize: 12, marginTop: 4 }}>
                  {isStreaming ? '运行中' : '就绪'}
                </div>
              </div>
            )}
            size={100}
          />
        </div>
      </div>
    </div>
  );
}
