import { Select } from 'antd';
import { Agent } from '../types/agent';

interface AgentSelectorProps {
  agents: Agent[];
  selectedAgent: string | null;
  onSelect: (agentId: string) => void;
}

export function AgentSelector({ agents, selectedAgent, onSelect }: AgentSelectorProps) {
  return (
    <div style={{ 
      padding: '16px 20px',
      backgroundColor: '#0a0e27',
      borderBottom: '1px solid #1a1f3a',
    }}>
      <Select
        style={{ width: '100%' }}
        placeholder="选择智能体"
        value={selectedAgent}
        onChange={onSelect}
        options={agents.map((agent) => ({
          label: `${agent.name} - ${agent.description}`,
          value: agent.id,
        }))}
        size="large"
      />
    </div>
  );
}
