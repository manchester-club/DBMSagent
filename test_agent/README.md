# PostgreSQL Code Coverage Multi-Agent System

基于 LangGraph 的多 Agent 代码覆盖率测试系统，通过智能 Agent 协作自动生成 SQL 测试用例来提高 PostgreSQL 函数的代码覆盖率。

## 🎯 项目简介

本项目实现了一个多 Agent 协作系统，用于自动化测试 PostgreSQL 代码覆盖率：

- **Supervisor**: 协调多个专家 Agent，负责任务派发和路由
- **Coverage Analyzer**: 分析代码覆盖率，生成 SQL 测试用例
- **SQL Tester**: 执行 SQL 测试用例，验证覆盖率提升
- **Code Explorer**: 获取函数源代码和调用关系信息

## 🏗️ 系统架构

```
┌─────────────┐
│  Frontend   │ (React + TypeScript + Ant Design)
│  (Port 5173) │
└──────┬──────┘
       │ WebSocket / HTTP
┌──────▼──────┐
│   Backend   │ (FastAPI + WebSocket)
│  (Port 8000) │
└──────┬──────┘
       │
┌──────▼──────────────────┐
│  LangGraph Multi-Agent   │
│  - Supervisor            │
│  - Coverage Analyzer     │
│  - SQL Tester            │
│  - Code Explorer         │
└──────┬───────────────────┘
       │
┌──────▼──────────────────┐
│  PostgreSQL + gcov       │
│  - Source Code           │
│  - Coverage Data         │
└──────────────────────────┘
```

## 📋 功能特性

- ✅ **多 Agent 协作**: Supervisor 智能派发任务给专家 Agent
- ✅ **代码覆盖率分析**: 自动收集和分析函数覆盖率
- ✅ **SQL 测试用例生成**: 基于种子 SQL 和代码分析生成测试用例
- ✅ **实时 WebSocket 通信**: 前端实时显示 Agent 执行过程
- ✅ **可视化界面**: React 前端展示测试流程和结果
- ✅ **批量测试**: 支持批量测试多个函数

## 🚀 快速开始

### 前置要求

- Python 3.8+
- Node.js 16+
- PostgreSQL 17.6 源代码
- gcov 工具
- Neo4j (可选，用于函数调用关系分析)

### 1. 克隆仓库

```bash
git clone <repository-url>
cd test_agent
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

**必需配置**:
- `DEEPSEEK_API_KEY`: DeepSeek API 密钥
- `POSTGRESQL_SRC_DIR`: PostgreSQL 源代码目录路径

### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 5. 启动后端服务

```bash
# 方式1: 使用启动脚本
./start_backend.sh

# 方式2: 直接运行
cd backend
python main.py
```

后端服务将在 `http://localhost:8000` 启动。

### 6. 启动前端服务

```bash
# 方式1: 使用启动脚本
./start_frontend.sh

# 方式2: 直接运行
cd frontend
npm run dev
```

前端服务将在 `http://localhost:5173` 启动。

### 7. 访问应用

打开浏览器访问 `http://localhost:5173`

## 📖 使用说明

### 基本使用

1. 在浏览器中打开前端界面
2. 选择 Agent（默认: `coverage_multi_agent`）
3. 在输入框中输入测试请求，例如：
   ```
   请提高 datan2 函数的代码覆盖率
   ```
4. 点击"发送"按钮
5. 系统会自动执行以下流程：
   - 收集初始覆盖率
   - 查找相关 SQL 种子
   - 生成 SQL 测试用例
   - 执行测试用例
   - 验证覆盖率提升

### 批量测试

```bash
python batch_test_functions.py
```

批量测试脚本会从 `待测函数集合.md` 中读取函数列表，逐个测试。

## 📁 项目结构

```
test_agent/
├── backend/                 # 后端服务
│   ├── main.py            # FastAPI 主服务
│   ├── agents/            # Agent 管理器
│   └── requirements.txt   # 后端依赖
├── frontend/              # 前端应用
│   ├── src/               # React 源代码
│   ├── package.json       # 前端依赖
│   └── vite.config.ts     # Vite 配置
├── langgraph/             # LangGraph Agent 实现
│   ├── coverage_multi_agent.py  # 多 Agent 系统
│   ├── nodes/             # 工具节点
│   │   ├── collect_coverage.py
│   │   ├── run_sql_test.py
│   │   ├── get_code_context.py
│   │   ├── search_nearest_seed.py
│   │   └── traverse_call_graph.py
│   └── requirements.txt   # LangGraph 依赖
├── log/                   # 日志文件目录
├── batch_test_functions.py  # 批量测试脚本
├── requirements.txt       # 合并的 Python 依赖
├── .env.example          # 环境变量示例
├── .gitignore            # Git 忽略文件
└── README.md             # 本文件
```

## 🔧 配置说明

### 环境变量

在 `.env` 文件中配置以下变量：

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | ✅ |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | ❌ |
| `LLM_MODEL` | 使用的 LLM 模型 | ❌ |
| `POSTGRESQL_SRC_DIR` | PostgreSQL 源代码目录 | ✅ |
| `NODES_FILE` | 函数知识图谱文件路径 | ❌ |
| `PIN_LOG_DIR` | 覆盖率日志目录 | ❌ |

### Agent 配置

Agent 的提示词和路由逻辑在 `langgraph/coverage_multi_agent.py` 中配置。

## 🛠️ 开发

### 代码结构

- **Supervisor**: 负责任务派发和路由决策
- **Coverage Analyzer**: 分析覆盖率，生成 SQL 测试用例
- **SQL Tester**: 执行 SQL 并验证覆盖率
- **Code Explorer**: 获取代码信息和调用关系

### 添加新工具

1. 在 `langgraph/nodes/` 目录下创建新的工具文件
2. 使用 `@tool` 装饰器定义工具
3. 在对应的 Agent 中绑定工具

## 📝 日志

日志文件保存在 `log/` 目录下，文件名格式：`{函数名}_{时间戳}.log`

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 多 Agent 框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架
- [React](https://react.dev/) - UI 框架

## 📚 相关文档

- [完整架构文档](COMPLETE_AGENT_ARCHITECTURE_AND_WORKFLOW.md)
- [Agent 工作流程](CORRECT_AGENT_WORKFLOW.md)
- [批量测试使用说明](BATCH_TEST_USAGE.md)
