# 🎉 前端服务已启动！

## ✅ 当前状态

### 后端服务
- **状态**: ✅ 运行中
- **地址**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 前端服务
- **状态**: ✅ 运行中
- **地址**: http://localhost:5173
- **Node.js**: v18.20.0
- **npm**: 10.5.0

## 🚀 立即使用

### 1. 访问前端界面

在浏览器中打开：
```
http://localhost:5173
```

### 2. 使用步骤

1. **选择智能体**
   - 在顶部下拉菜单选择要使用的智能体
   - 当前可用：
     - `ollama_agent_with_tools` - PostgreSQL代码分析智能体
     - `coverage_multi_agent` - Coverage Multi-Agent

2. **发送消息**
   - 在输入框中输入问题
   - 按 Enter 或点击"发送"按钮
   - 支持多行输入（Shift+Enter 换行）

3. **查看响应**
   - 实时流式输出（逐字显示）
   - 工具调用会显示为可展开的卡片
   - 点击"展开"查看工具参数和结果

4. **导出对话**
   - 点击"导出"按钮保存对话记录为 TXT 文件

## 📋 功能特性

- ✅ **实时流式输出** - LLM 回复逐字显示
- ✅ **工具调用可视化** - 可展开/折叠查看详情
- ✅ **代码高亮** - 使用 Monaco Editor 显示代码
- ✅ **对话导出** - 保存为 TXT 格式
- ✅ **多智能体切换** - 随时切换不同智能体
- ✅ **响应式界面** - 适配不同屏幕尺寸

## 🔧 服务管理

### 查看服务状态

```bash
# 检查端口
netstat -tlnp | grep -E "(5173|8000)"

# 查看进程
ps aux | grep -E "(vite|python.*main.py)"
```

### 停止服务

```bash
# 停止前端（查找进程后 kill）
ps aux | grep vite
kill <PID>

# 停止后端
ps aux | grep "python.*main.py"
kill <PID>
```

### 重启服务

**方式1: 使用启动脚本**
```bash
cd /public/home/rongyankai/test_agent
./start_all.sh
```

**方式2: 手动启动**

终端1 - 后端：
```bash
cd backend
python3 main.py
```

终端2 - 前端：
```bash
cd frontend
export PATH="$HOME/.local/nodejs/node-v18.20.0-linux-x64/bin:$PATH"
npm run dev
```

## 🎯 使用示例

### 示例1: 查询函数信息

选择智能体：`ollama_agent_with_tools`

输入：
```
查询函数 date2timestamptz_opt_overflow 的调用关系
```

系统会：
1. LLM 分析查询意图
2. 自动调用相关工具（query_function_info, query_function_callers 等）
3. 流式显示结果

### 示例2: 覆盖率分析

选择智能体：`coverage_multi_agent`

输入：
```
请分析 EncodeSpecialDate 函数：
1) 用 Get_Code_Context 获取其源代码
2) 用 Traverse_Call_Graph 向上遍历调用关系
3) 用 Collect_Coverage 收集覆盖率
```

系统会：
1. Supervisor 协调多个专家 Agent
2. 执行相应的工具调用
3. 显示完整的分析结果

## ⚠️ 注意事项

1. **Neo4j 服务**
   - 确保 Neo4j 正在运行（如果使用相关智能体）
   - 检查：`cd neo4j && bash start_neo4j.sh status`

2. **Ollama 服务**
   - 确保 Ollama 正在运行并已安装模型
   - 检查：`ollama list`

3. **网络连接**
   - 前端需要连接到后端（localhost:8000）
   - 如果连接失败，检查后端是否运行

4. **浏览器兼容性**
   - 推荐使用 Chrome、Firefox、Edge 等现代浏览器
   - 需要支持 WebSocket

## 🐛 故障排查

### 前端无法访问

1. 检查服务是否运行：`ps aux | grep vite`
2. 检查端口：`netstat -tlnp | grep 5173`
3. 查看前端日志（终端输出）

### 无法连接到后端

1. 检查后端是否运行：`curl http://localhost:8000/`
2. 检查 CORS 配置
3. 查看后端日志：`tail -f backend/server.log`

### 工具调用不显示

1. 检查智能体是否正确初始化
2. 查看浏览器控制台错误
3. 检查 WebSocket 连接状态

## 📝 下一步

1. ✅ 打开浏览器访问 http://localhost:5173
2. ✅ 选择智能体
3. ✅ 开始对话
4. ✅ 体验流式输出和工具调用功能

享受使用！🎉
