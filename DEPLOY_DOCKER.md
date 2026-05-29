# ShuyuanCore Docker 部署指南

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/ElementaAI/Shuyuancore.git
cd Shuyuancore
```

### 2. 配置环境变量

复制环境变量模板并填写 API Key：

```bash
cp .env.docker .env
# 编辑 .env 文件，填入你的 API Key
```

**必需的环境变量**：
- `DASHSCOPE_API_KEY` - 阿里云 DashScope API Key
- `DEEPSEEK_API_KEY` - DeepSeek API Key

**可选的环境变量**：
- `HOST_PORT` - 主机端口（默认：8005）
- `ENABLE_PROACTIVE` - 启用主动发起（默认：false）

### 3. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 检查健康状态
curl http://localhost:8005/health
```

### 4. 使用 CLI（可选）

```bash
# 启动 CLI 交互模式
docker-compose --profile cli up cli
```

## 高级配置

### 自定义配置

将自定义配置文件放在 `./config/` 目录，然后在 `.env` 中指定：

```bash
SHUYUANCORE_CONFIG=/app/config/custom.yaml
```

### 数据持久化

数据默认持久化在 `./data/` 目录：
- `data/state.db` - SQLite 数据库
- `data/chroma/` - ChromaDB 向量库
- `data/logs/` - 日志文件

### 资源限制

在 `docker-compose.yaml` 中已配置资源限制：
- CPU: 0.5 - 2.0 核心
- 内存：512MB - 2GB

可根据实际情况调整。

## 故障排查

### 容器无法启动

```bash
# 查看容器日志
docker-compose logs shuyuancore

# 检查环境变量
docker-compose config
```

### 健康检查失败

```bash
# 手动执行健康检查
docker exec shuyuancore curl -f http://localhost:8005/health

# 查看容器状态
docker inspect shuyuancore
```

### 数据库迁移问题

```bash
# 手动执行迁移
docker exec shuyuancore alembic upgrade head

# 查看当前版本
docker exec shuyuancore alembic current
```

## 停止与清理

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷（谨慎使用）
docker-compose down -v

# 查看容器状态
docker-compose ps
```

## 更新

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

## 生产环境建议

1. **使用 Docker Swarm 或 Kubernetes** 进行编排
2. **配置反向代理**（Nginx/Traefik）处理 SSL 和负载均衡
3. **使用外部数据库**（PostgreSQL）替代 SQLite
4. **配置日志收集**（ELK/Loki）
5. **设置监控告警**（Prometheus/Grafana）

## 安全注意事项

- 不要将 `.env` 文件提交到 Git
- 定期更新基础镜像（`python:3.11-slim`）
- 使用非 root 用户运行（已配置）
- 限制容器网络访问（已配置独立网络）
- 定期备份 `data/` 目录
