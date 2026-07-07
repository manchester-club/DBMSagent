import { Tag } from 'antd';
import { BulbOutlined } from '@ant-design/icons';
import { Agent } from '../types/agent';

interface AgentTreeProps {
  agents: Agent[];
  selectedAgent: string | null;
  activeAgents?: string[];
}

export function AgentTree({ agents, selectedAgent, activeAgents = [] }: AgentTreeProps) {
  const activeCount = activeAgents.length || (selectedAgent ? 1 : 0);

  return (
    <div style={{
      backgroundColor: '#141829',
      borderRadius: 8,
      padding: 16,
      border: '1px solid #1a1f3a',
    }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: 16,
      }}>
        <h4 style={{ margin: 0, color: '#e8e8e8', fontSize: 14, fontWeight: 600 }}>AGENT TREE</h4>
        <Tag color="default" style={{ margin: 0 }}>{activeCount}</Tag>
      </div>
      
      <div style={{ color: '#e8e8e8' }}>
        {agents.map((agent) => {
          const isActive = selectedAgent === agent.id || activeAgents.includes(agent.id);
          return (
            <div
              key={agent.id}
              style={{
                padding: '8px 12px',
                marginBottom: 8,
                backgroundColor: isActive ? '#1a2332' : 'transparent',
                borderRadius: 4,
                border: isActive ? '1px solid #1890ff' : '1px solid transparent',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <div style={{ 
                width: 8, 
                height: 8, 
                borderRadius: '50%',
                backgroundColor: isActive ? '#52c41a' : '#8c8c8c',
              }} />
              <BulbOutlined style={{ color: isActive ? '#52c41a' : '#8c8c8c' }} />
              <span style={{ 
                color: isActive ? '#e8e8e8' : '#8c8c8c',
                fontSize: 13,
              }}>
                {agent.name}
              </span>
              {isActive && (
                <Tag color="green" style={{ margin: 0, fontSize: 10 }}>1x</Tag>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
