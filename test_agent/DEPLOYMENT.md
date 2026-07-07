# 部署指南

## 本地开发环境

### 1. 系统要求

- Python 3.8+
- Node.js 16+
- PostgreSQL 17.6 源代码
- gcov 工具

### 2. 安装步骤

#### 后端

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 启动后端
cd backend
python main.py
```

#### 前端

```bash
# 安装 Node.js 依赖
cd frontend
npm install

# 启动开发服务器
npm run dev
```

## 生产环境部署

### Docker 部署（推荐）

#### 1. 创建 Dockerfile

**backend/Dockerfile**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**frontend/Dockerfile**:
```dockerfile
FROM node:18-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

#### 2. 使用 Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - POSTGRESQL_SRC_DIR=${POSTGRESQL_SRC_DIR}
    volumes:
      - ${POSTGRESQL_SRC_DIR}:/postgresql-src:ro
      - ./log:/app/log

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
```

启动服务：
```bash
docker-compose up -d
```

### 传统部署

#### 后端部署

1. 使用 systemd 管理服务

创建 `/etc/systemd/system/coverage-agent.service`:

```ini
[Unit]
Description=Coverage Multi-Agent Backend
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/test_agent/backend
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable coverage-agent
sudo systemctl start coverage-agent
```

2. 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 前端部署

1. 构建生产版本

```bash
cd frontend
npm run build
```

2. 部署到 Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
    }

    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 环境变量配置

生产环境建议使用环境变量管理工具或配置管理服务：

- **开发环境**: `.env` 文件
- **生产环境**: 系统环境变量或配置管理服务（如 AWS Secrets Manager, HashiCorp Vault）

## 监控和日志

### 日志管理

- 后端日志: `log/` 目录
- 系统日志: 使用 systemd journal 或日志聚合服务

### 监控

建议集成以下监控工具：
- Prometheus + Grafana
- Sentry (错误追踪)
- ELK Stack (日志分析)

## 安全建议

1. **API 密钥安全**
   - 不要在代码中硬编码 API 密钥
   - 使用环境变量或密钥管理服务
   - 定期轮换密钥

2. **网络安全**
   - 使用 HTTPS
   - 配置防火墙规则
   - 限制 API 访问

3. **数据安全**
   - 定期备份日志和配置
   - 保护源代码目录访问权限

## 故障排查

### 常见问题

1. **后端无法启动**
   - 检查 Python 版本和依赖
   - 检查环境变量配置
   - 查看日志文件

2. **前端无法连接后端**
   - 检查后端服务是否运行
   - 检查 CORS 配置
   - 检查网络连接

3. **WebSocket 连接失败**
   - 检查防火墙设置
   - 检查代理配置
   - 查看浏览器控制台错误

## 性能优化

1. **后端优化**
   - 使用异步处理
   - 连接池管理
   - 缓存机制

2. **前端优化**
   - 代码分割
   - 懒加载
   - CDN 加速
