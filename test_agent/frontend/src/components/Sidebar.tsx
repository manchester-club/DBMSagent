import { useState, useEffect } from 'react';
import { Message } from '../types/agent';

interface SidebarProps {
  messages: Message[];
}

interface TargetInfo {
  functionName: string;
  filePath: string;
  initialCoverage: number | null;
  currentCoverage: number | null;
}

interface WorkflowStep {
  step: number;
  agent: string;
  title: string;
  status: 'pending' | 'active' | 'completed';
}

export function Sidebar({ messages }: SidebarProps) {
  const [targetInfo, setTargetInfo] = useState<TargetInfo>({
    functionName: '-',
    filePath: '-',
    initialCoverage: null,
    currentCoverage: null,
  });

  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([]);

  useEffect(() => {
    // 从消息中提取测试目标信息
    const collectCoverageMessages = messages.filter(
      (msg) => msg.toolCall?.toolName === 'Collect_Coverage'
    );

    console.log('Sidebar: Collect_Coverage messages:', collectCoverageMessages.length);
    
    if (collectCoverageMessages.length > 0) {
      // 辅助函数：检查结果是否成功
      const isSuccessResult = (result: any): boolean => {
        if (!result) return false;
        if (typeof result === 'string') {
          try {
            const parsed = JSON.parse(result);
            return parsed.status === 'Success' || (parsed.status !== 'Error' && parsed.coverage !== undefined);
          } catch (e) {
            // 如果无法解析，假设是成功的（可能是旧格式）
            return true;
          }
        }
        if (typeof result === 'object' && result !== null) {
          return result.status === 'Success' || (result.status !== 'Error' && result.coverage !== undefined);
        }
        return false;
      };

      // 找到第一个成功的覆盖率结果（用于初始信息）
      let firstSuccessfulCoverage = null;
      for (const msg of collectCoverageMessages) {
        if (msg.toolCall?.result && isSuccessResult(msg.toolCall.result)) {
          firstSuccessfulCoverage = msg;
          break;
        }
      }

      // 找到最后一个成功的覆盖率结果（用于当前覆盖率）
      let lastSuccessfulCoverage = null;
      for (let i = collectCoverageMessages.length - 1; i >= 0; i--) {
        const msg = collectCoverageMessages[i];
        if (msg.toolCall?.result && isSuccessResult(msg.toolCall.result)) {
          lastSuccessfulCoverage = msg;
          break;
        }
      }

      // 如果没有找到成功的结果，使用第一个和最后一个（可能是旧格式）
      const firstCoverage = firstSuccessfulCoverage || collectCoverageMessages[0];
      const lastCoverage = lastSuccessfulCoverage || collectCoverageMessages[collectCoverageMessages.length - 1];

      // 辅助函数：解析结果
      const parseResult = (result: any): any => {
        if (typeof result === 'string') {
          try {
            // 尝试解析 JSON
            const parsed = JSON.parse(result);
            console.log('Sidebar: Successfully parsed JSON:', parsed);
            return parsed;
          } catch (e) {
            // 如果解析失败，尝试从字符串中提取信息
            console.warn('Sidebar: Failed to parse result as JSON, trying to extract from string:', result.substring(0, 200));
            // 尝试使用正则表达式提取关键信息（支持多种格式）
            const coverageMatch = result.match(/['"]?coverage['"]?\s*[:=]\s*([\d.]+)/i);
            const functionNameMatch = result.match(/['"]?function_name['"]?\s*[:=]\s*['"]([^'"]+)['"]/i) ||
                                      result.match(/function_name[:\s]+([^\s,}]+)/i);
            const filePathMatch = result.match(/['"]?file_path['"]?\s*[:=]\s*['"]([^'"]+)['"]/i) ||
                                  result.match(/file_path[:\s]+['"]?([^'",}]+)['"]?/i);
            
            const parsed: any = {};
            if (coverageMatch) {
              parsed.coverage = parseFloat(coverageMatch[1]);
              console.log('Sidebar: Extracted coverage:', parsed.coverage);
            }
            if (functionNameMatch) {
              parsed.function_name = functionNameMatch[1].trim();
              console.log('Sidebar: Extracted function_name:', parsed.function_name);
            }
            if (filePathMatch) {
              parsed.file_path = filePathMatch[1].trim();
              console.log('Sidebar: Extracted file_path:', parsed.file_path);
            }
            
            if (Object.keys(parsed).length > 0) {
              console.log('Sidebar: Final parsed object:', parsed);
              return parsed;
            }
            console.warn('Sidebar: Could not extract any information from result string');
            return null;
          }
        }
        // 如果已经是对象，直接返回
        if (typeof result === 'object' && result !== null) {
          console.log('Sidebar: Result is already an object:', result);
          return result;
        }
        return null;
      };

      // 解析第一个成功的覆盖率结果（用于初始信息）
      if (firstCoverage.toolCall?.result) {
        console.log('Sidebar: First coverage raw result:', firstCoverage.toolCall.result);
        const result = parseResult(firstCoverage.toolCall.result);
        console.log('Sidebar: First coverage parsed result:', result);
        
        if (result && typeof result === 'object') {
          const obj = result as any;
          
          // 检查是否是成功的结果（status 为 'Success' 或 coverage > 0）
          const isSuccess = obj.status === 'Success' || 
                           (obj.status !== 'Error' && obj.coverage !== undefined && obj.coverage !== null && obj.coverage > 0);
          
          if (!isSuccess) {
            console.warn('Sidebar: First coverage result is not successful, status:', obj.status, 'coverage:', obj.coverage);
            // 如果第一个结果不成功，尝试查找下一个成功的结果
            for (let i = 1; i < collectCoverageMessages.length; i++) {
              const msg = collectCoverageMessages[i];
              if (msg.toolCall?.result) {
                const nextResult = parseResult(msg.toolCall.result);
                if (nextResult && typeof nextResult === 'object') {
                  const nextObj = nextResult as any;
                  const nextIsSuccess = nextObj.status === 'Success' || 
                                       (nextObj.status !== 'Error' && nextObj.coverage !== undefined && nextObj.coverage !== null && nextObj.coverage > 0);
                  if (nextIsSuccess) {
                    console.log('Sidebar: Found successful coverage result at index', i);
                    // 使用这个成功的结果
                    const newInfo: Partial<TargetInfo> = {};
                    if (nextObj.function_name || nextObj.functionName) {
                      newInfo.functionName = nextObj.function_name || nextObj.functionName;
                    }
                    if (nextObj.file_path || nextObj.filePath) {
                      newInfo.filePath = nextObj.file_path || nextObj.filePath;
                    }
                    if (nextObj.coverage !== undefined && nextObj.coverage !== null) {
                      newInfo.initialCoverage = typeof nextObj.coverage === 'number' ? nextObj.coverage : parseFloat(nextObj.coverage);
                    }
                    setTargetInfo((prev) => ({
                      ...prev,
                      ...newInfo,
                    }));
                    break;
                  }
                }
              }
            }
          } else {
            // 第一个结果就是成功的，直接使用
            const newInfo: Partial<TargetInfo> = {};
            
            // 提取函数名
            if (obj.function_name || obj.functionName) {
              newInfo.functionName = obj.function_name || obj.functionName;
              console.log('Sidebar: Setting functionName:', newInfo.functionName);
            }
            
            // 提取文件路径
            if (obj.file_path || obj.filePath) {
              newInfo.filePath = obj.file_path || obj.filePath;
              console.log('Sidebar: Setting filePath:', newInfo.filePath);
            }
            
            // 提取初始覆盖率（只使用成功的覆盖率）
            if (obj.coverage !== undefined && obj.coverage !== null && obj.coverage > 0) {
              newInfo.initialCoverage = typeof obj.coverage === 'number' ? obj.coverage : parseFloat(obj.coverage);
              console.log('Sidebar: Setting initialCoverage:', newInfo.initialCoverage);
            }
            
            setTargetInfo((prev) => ({
              ...prev,
              ...newInfo,
            }));
          }
        }
      }

      // 解析最后一个覆盖率结果（用于当前覆盖率）
      if (lastCoverage.toolCall?.result && lastCoverage !== firstCoverage) {
        console.log('Sidebar: Last coverage raw result:', lastCoverage.toolCall.result);
        const result = parseResult(lastCoverage.toolCall.result);
        console.log('Sidebar: Last coverage parsed result:', result);
        
        if (result && typeof result === 'object') {
          const obj = result as any;
          const updates: Partial<TargetInfo> = {};
          
          // 如果最后一个结果中有函数名和文件路径，也更新（可能更准确）
          if (obj.function_name || obj.functionName) {
            updates.functionName = obj.function_name || obj.functionName;
          }
          if (obj.file_path || obj.filePath) {
            updates.filePath = obj.file_path || obj.filePath;
          }
          
          // 更新当前覆盖率
          if (obj.coverage !== undefined && obj.coverage !== null) {
            updates.currentCoverage = typeof obj.coverage === 'number' ? obj.coverage : parseFloat(obj.coverage);
            console.log('Sidebar: Setting currentCoverage:', updates.currentCoverage);
          }
          
          setTargetInfo((prev) => ({
            ...prev,
            ...updates,
          }));
        }
      } else if (lastCoverage === firstCoverage && firstCoverage.toolCall?.result) {
        // 如果只有一个结果，同时设置初始和当前覆盖率
        const result = parseResult(firstCoverage.toolCall.result);
        if (result && typeof result === 'object') {
          const obj = result as any;
          if (obj.coverage !== undefined && obj.coverage !== null) {
            const coverage = typeof obj.coverage === 'number' ? obj.coverage : parseFloat(obj.coverage);
            setTargetInfo((prev) => ({
              ...prev,
              initialCoverage: coverage,
              currentCoverage: coverage,
            }));
          }
        }
      }
    }

    // 从消息中提取执行步骤
    const steps: WorkflowStep[] = [];
    let stepCount = 1;

    messages.forEach((msg) => {
      if (msg.type === 'dispatch' && msg.agent) {
        steps.push({
          step: stepCount++,
          agent: msg.agent,
          title: `派发 ${msg.agent}`,
          status: 'completed',
        });
      }
    });

    // 更新最后一步为 active（如果正在流式传输）
    if (steps.length > 0) {
      steps[steps.length - 1].status = 'active';
    }

    setWorkflowSteps(steps);
  }, [messages]);

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        overflowY: 'auto', // 允许垂直滚动
        overflowX: 'hidden', // 防止水平滚动
        borderLeft: '1px solid #1a1f3a',
        backgroundColor: '#0a0e27',
      }}
    >
      {/* 测试目标 */}
      <div
        style={{
          backgroundColor: '#141829',
          borderRadius: 8,
          padding: 16,
          border: '1px solid #1a1f3a',
        }}
      >
        <h3
          style={{
            margin: '0 0 16px 0',
            color: '#e8e8e8',
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          🎯 测试目标
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div
              style={{
                color: '#8c8c8c',
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              函数名
            </div>
            <div
              style={{
                color: '#e8e8e8',
                fontSize: 14,
                fontFamily: 'monospace',
              }}
            >
              {targetInfo.functionName}
            </div>
          </div>
          <div>
            <div
              style={{
                color: '#8c8c8c',
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              文件路径
            </div>
            <div
              style={{
                color: '#e8e8e8',
                fontSize: 12,
                fontFamily: 'monospace',
                wordBreak: 'break-word',
              }}
            >
              {targetInfo.filePath}
            </div>
          </div>
          <div>
            <div
              style={{
                color: '#8c8c8c',
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              初始覆盖率
            </div>
            <div
              style={{
                color: '#e8e8e8',
                fontSize: 14,
                fontFamily: 'monospace',
              }}
            >
              {targetInfo.initialCoverage !== null
                ? `${targetInfo.initialCoverage.toFixed(2)}%`
                : '-'}
            </div>
          </div>
          <div>
            <div
              style={{
                color: '#8c8c8c',
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              当前覆盖率
            </div>
            <div
              style={{
                color: '#e8e8e8',
                fontSize: 14,
                fontFamily: 'monospace',
                fontWeight: 600,
              }}
            >
              {targetInfo.currentCoverage !== null
                ? `${targetInfo.currentCoverage.toFixed(2)}%`
                : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* 执行步骤 */}
      <div
        style={{
          backgroundColor: '#141829',
          borderRadius: 8,
          padding: 16,
          border: '1px solid #1a1f3a',
        }}
      >
        <h3
          style={{
            margin: '0 0 16px 0',
            color: '#e8e8e8',
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          🔄 执行步骤
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {workflowSteps.length === 0 ? (
            <div
              style={{
                color: '#8c8c8c',
                fontSize: 12,
                textAlign: 'center',
                padding: '20px 0',
              }}
            >
              暂无执行步骤
            </div>
          ) : (
            workflowSteps.map((step) => (
              <div
                key={step.step}
                style={{
                  padding: '10px 12px',
                  backgroundColor:
                    step.status === 'active'
                      ? '#1a1f3a'
                      : step.status === 'completed'
                      ? '#0a0e27'
                      : '#0a0e27',
                  borderRadius: 6,
                  border:
                    step.status === 'active'
                      ? '1px solid #1890ff'
                      : '1px solid #1a1f3a',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <div
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    backgroundColor:
                      step.status === 'active'
                        ? '#1890ff'
                        : step.status === 'completed'
                        ? '#52c41a'
                        : '#8c8c8c',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff',
                    fontSize: 12,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {step.status === 'completed' ? '✓' : step.step}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      color: '#e8e8e8',
                      fontSize: 13,
                      fontWeight: 500,
                    }}
                  >
                    {step.title}
                  </div>
                  <div
                    style={{
                      color: '#8c8c8c',
                      fontSize: 11,
                      marginTop: 2,
                    }}
                  >
                    {step.agent}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
