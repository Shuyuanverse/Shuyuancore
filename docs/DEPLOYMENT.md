# ShuyuanCore 部署文档

**版本**：v1.0 | **更新日期**：2026-05-27 | **对应 Phase**：10

---

## 系统要求

| 组件 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Ubuntu 22.04+ / Debian 12+ | Ubuntu 24.04 LTS |
| Python | 3.10+ | 3.12 |
| 内存 | 2GB RAM | 8GB RAM |
| 磁盘 | 10GB 可用空间 | 50GB SSD |
| Docker（可选） | 24.0+ | 24.0+ |

---

## 一键安装

```bash
curl -sSL https://github.com/Shuyuanverse/Shuyuancore/releases/latest/download/install.sh | bash
```

安装完成后：
1. 编辑配置文件：`nano /opt/shuyuancore/.env`
2. 填入 API Key（至少设置 `DASHSCOPE_API_KEY` 或 `DEEPSEEK_API_KEY`）
3. 启动服务：`systemctl start shuyuancore`
4. 查看状态：`systemctl status shuyuancore`

---

## 手动安装

### 1. 安装依赖

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip python3-venv curl
```

### 2. 克隆仓库

```bash
sudo mkdir -p /opt/shuyuancore
sudo chown $USER:$USER /opt/shuyuancore
git clone https://github.com/Shuyuanverse/Shuyuancore.git /opt/shuyuancore
cd /opt/shuyuancore
```

### 3. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
nano .env
```

### 5. 创建数据目录

```bash
mkdir -p data/logs data/chroma
```

### 6. 启动服务

```bash
# 直接启动
uvicorn src.gateway.api_server:create_app --factory --host 0.0.0.0 --port 8005

# 或通过 systemd
sudo cp deploy/systemd/shuyuancore.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shuyuancore
```

---

## Docker 部署

### 前提条件

- 安装 Docker 24.0+ 和 Docker Compose v2

### 快速启动

```bash
# 克隆仓库
git clone https://github.com/Shuyuanverse/Shuyuancore.git
cd Shuyuancore

# 创建 .env 文件
cp .env.example .env
# 编辑 .env 填入 API Key

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 健康检查

```bash
curl http://localhost:8005/health
# 预期响应：{"status":"healthy","version":"1.3.0","database":"connected"}
```

---

## 配置说明

### 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | 推荐 | 阿里云 DashScope API Key（主模型） |
| `DEEPSEEK_API_KEY` | 推荐 | DeepSeek API Key（复盘LLM/备选） |
| `OPENAI_API_KEY` | 否 | OpenAI API Key（可选提供商） |
| `CURSOR_SECRET` | 否 | 游标分页签名密钥（默认自动生成） |

### 配置文件

所有可配置参数在 `config/default.yaml` 中：

```yaml
deploy:
  port: 8005
  log_level: info

security:
  rate_limit_per_minute: 60
  api_keys: []
  cursor_secret: ""
```

> **注意**：API Key 等敏感信息通过环境变量注入，不写入配置文件。

---

## 启动/停止/重启

### systemd 方式

```bash
# 启动
sudo systemctl start shuyuancore

# 停止
sudo systemctl stop shuyuancore

# 重启
sudo systemctl restart shuyuancore

# 查看状态
sudo systemctl status shuyuancore

# 查看日志
journalctl -u shuyuancore -f
```

### Docker 方式

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看日志
docker-compose logs -f
```

---

## Nginx 反向代理配置

1. 修改 `deploy/nginx/shuyuancore.conf`，替换 `your-domain.com` 为你的域名
2. 配置 SSL 证书（建议使用 Let's Encrypt）：

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

3. 启用配置：

```bash
sudo cp deploy/nginx/shuyuancore.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/shuyuancore.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 升级与回滚

### 升级

```bash
# systemd 方式
cd /opt/shuyuancore
sudo -u shuyuancore git pull origin main
sudo -u shuyuancore ./venv/bin/pip install -e .
sudo systemctl restart shuyuancore

# Docker 方式
docker-compose pull
docker-compose up -d
```

### 回滚

```bash
# systemd 方式
cd /opt/shuyuancore
sudo -u shuyuancore git checkout <previous-commit>
sudo -u shuyuancore ./venv/bin/pip install -e .
sudo systemctl restart shuyuancore

# Docker 方式
docker-compose down
docker-compose up -d  # 使用上次构建的镜像
```

---

## 故障排查

### 服务无法启动

**问题**：`systemctl start shuyuancore` 失败

**检查步骤**：

```bash
# 查看详细错误
journalctl -u shuyuancore -n 50 --no-pager

# 确认 .env 存在
ls -la /opt/shuyuancore/.env

# 确认 Python 虚拟环境
/opt/shuyuancore/venv/bin/python -c "import uvicorn; print('OK')"

# 手动启动测试
cd /opt/shuyuancore && source venv/bin/activate && uvicorn src.gateway.api_server:create_app --factory --host 0.0.0.0 --port 8005
```

### 健康检查失败

**问题**：`/health` 返回非 200 状态码

**可能原因**：
- 数据库文件权限问题：`chown -R shuyuancore:shuyuancore /opt/shuyuancore/data`
- 端口被占用：`ss -tlnp | grep 8005`
- API Key 未配置：检查 `.env` 文件

### Docker 部署问题

**问题**：`docker-compose up` 启动失败

```bash
# 查看容器日志
docker-compose logs shuyuancore

# 检查健康检查状态
docker inspect $(docker-compose ps -q shuyuancore) | jq '.[0].State.Health'

# 确认 API Key 已传入
docker-compose config | grep API_KEY
```

### 日志查看

```bash
# 应用日志
tail -f /opt/shuyuancore/data/logs/app.log

# 审计日志
tail -f /opt/shuyuancore/data/logs/audit.log

# systemd 日志
journalctl -u shuyuancore -f

# Docker 日志
docker-compose logs -f
```

---

## 性能调优

### uvicorn Worker 数

单 worker 适合大多数场景。如需更高并发，可在 systemd service 中调整 `--workers` 参数：

```ini
ExecStart=... --workers 4
```

> **注意**：多 worker 模式下，内存中的状态（如限流令牌桶、审批流）不共享。如需高可用，建议使用 Docker + 负载均衡。

### SQLite WAL 模式

数据库已默认启用 WAL 模式，保证写入不阻塞读取。无需额外配置。

---

## 技术债务

| 项目 | 说明 | 计划 |
|------|------|------|
| WebSocket 实时推送 | 当前使用 SSE 满足流式需求，WebSocket 端点未实现 | 后续版本 |
| /memory/* REST API | 记忆操作通过 Agent 内部自动完成，未暴露 REST 端点 | 后续版本 |
| /skills/curate API | Curator 回收逻辑未暴露 API 端点 | 后续版本 |
| Prometheus 指标 | 未集成 metrics 采集 | 后续版本 |

---

*文档结束 | ShuyuanCore 部署文档 v1.0 | 2026-05-27*