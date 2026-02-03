# STRUT LangGraph 单元测试生成系统

本项目是基于 LangGraph 实现的自动化 C 代码（PostgreSQL）单元测试生成系统。它通过多智能体协作（Multi-Agent Collaboration）来完成上下文提取、测试生成、编译运行及覆盖率反馈优化的闭环流程。

## 核心架构 (`langgraph_strut/`)

该模块将测试生成任务拆解为以下专家智能体和节点：

1.  **Manager Agent** (`agents.py`): 系统的“大脑”，负责根据当前状态（是否有代码、是否运行成功、覆盖率是否达标）调度其他 Agent。
2.  **Test Generator Agent** (`agents.py`): 负责生成和优化 C 测试代码，利用 LLM (Gemini/DeepSeek) 生成高质量的测试用例。
3.  **Extract Context Node**: 自动解析 C 文件，提取目标函数定义、结构体信息及宏定义。
4.  **Execution Node**: 自动生成 PostgreSQL 测试套件骨架（Makefile/SQL），并执行编译与测试运行。
5.  **Coverage Node**: 采集测试运行后的代码覆盖率报告，为下一轮优化提供数据支持。

## 快速开始

### 1. 环境准备
确保已安装必要的依赖：
```bash
pip install langgraph langchain langchain-community psycopg2-binary requests
```

### 2. 配置 API Key
在 `model.py` 中填入您的 OpenRouter API Key：
```python
DEEPSEEK_API_KEY = "您的 API KEY"
```

### 3. 运行命令
在项目根目录下执行以下命令来为指定函数生成测试套件：

```bash
# 格式：PYTHONPATH=$PWD python3 -m [模块路径] [C文件路径] -f [函数名]
PYTHONPATH=$PWD python3 -m STRUT.langgraph_strut.workflow src/backend/utils/adt/int.c -f int2out
```

> **注意**：命令中的 `STRUT` 对应项目所在的父目录名，请确保 Python 搜索路径正确。

## 流程特性
- **自动化迭代**：如果初始生成的测试用例覆盖率不足，Manager Agent 会自动调度 Test Generator 参考覆盖率报告进行修复和增强，最大支持 3 次迭代。
- **确定性路由**：在关键跳转点结合了硬编码逻辑与 LLM 决策，兼顾灵活性与稳定性。
- **详细调试日志**：实时输出 Prompt 内容、LLM 响应及各节点状态，方便监控生成进度。
