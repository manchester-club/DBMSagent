import { Button, Typography, Collapse } from 'antd';
import { ToolCall } from '../types/agent';
import { CodeViewer } from './CodeViewer';
import { DownOutlined, UpOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { Panel } = Collapse;

interface ToolCallCardProps {
  toolCall: ToolCall;
  onToggle: () => void;
}

export function ToolCallCard({ toolCall, onToggle }: ToolCallCardProps) {
  const isExpanded = toolCall.expanded || false;

  return (
    <div style={{
      marginTop: 8,
      padding: '8px 12px',
      backgroundColor: '#0a0e27',
      borderRadius: 4,
      border: '1px solid #1a1f3a',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text strong style={{ color: '#e8e8e8', marginRight: 8 }}>
          🔧 {toolCall.toolName}
        </Text>
        <Button
          type="link"
          size="small"
          icon={isExpanded ? <UpOutlined /> : <DownOutlined />}
          onClick={onToggle}
          style={{ color: '#1890ff', padding: 0 }}
        >
          {isExpanded ? '折叠' : '展开'}
        </Button>
      </div>

      {isExpanded && (
        <div style={{ marginTop: 12 }}>
          <Collapse 
            size="small"
            style={{ backgroundColor: '#141829' }}
          >
            <Panel 
              header={<span style={{ color: '#e8e8e8' }}>参数</span>} 
              key="args"
            >
              <CodeViewer
                code={JSON.stringify(toolCall.args, null, 2)}
                language="json"
              />
            </Panel>
            {toolCall.result && (
              <Panel 
                header={<span style={{ color: '#e8e8e8' }}>结果</span>} 
                key="result"
              >
                <CodeViewer
                  code={
                    typeof toolCall.result === 'string'
                      ? toolCall.result
                      : JSON.stringify(toolCall.result, null, 2)
                  }
                  language="json"
                />
              </Panel>
            )}
          </Collapse>
        </div>
      )}
    </div>
  );
}
