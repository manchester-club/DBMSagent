# 安装说明

## 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

## 2. 配置环境变量

创建 `.env` 文件：

```bash
# PostgreSQL配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# Neo4j配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM配置（Ollama）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=your_model_name

# 或使用OpenAI API
# OPENAI_API_KEY=your_api_key
```

## 3. 确保数据库已配置

- PostgreSQL：确保已创建数据库并包含目标代码库的编译信息
- Neo4j：确保已导入调用关系图数据

## 4. 运行测试

```bash
# 测试单个函数
python3 -c "from langgraph.coverage_multi_agent import run_test; run_test('dcosd')"

# 批量测试
python3 batch_test_functions.py --start-index 0 --end-index 10
```
