# Security Policy

## 报告安全漏洞

如果你发现 ShuyuanCore 中存在安全漏洞，请通过以下方式联系我们：

- **邮箱**：[shuyuancore@example.com](mailto:shuyuancore@example.com)
- **邮件主题**：请以 `[SECURITY]` 开头

**请不要通过公开 Issue 报告安全漏洞**，以便我们有时间在漏洞被利用之前进行修复。

---

## 响应承诺

- 我们会在收到报告后 **3 个工作日内** 确认收到
- 我们会在确认问题后 **7 个工作日内** 提供初步评估
- 我们会定期向报告者更新修复进展
- 漏洞修复后，我们会发布安全公告并致谢

---

## 支持范围

| 版本 | 是否接收安全更新 |
|------|-----------------|
| 最新稳定版 | 是 |
| main 分支 | 是 |

---

## 负责任披露

我们感谢负责任的漏洞披露。在公开披露之前，我们请求：

1. 给我们合理的时间来识别和解决该问题
2. 避免利用该漏洞来进一步探索系统
3. 不要在修复前公开披露该漏洞
4. 不要求金钱奖励即可披露

---

## 安全最佳实践

如果你正在部署 ShuyuanCore，建议遵循以下安全实践：

- **API Key 管理**：始终通过环境变量注入 API Key，不要写入配置文件或代码
- **网络隔离**：生产环境部署时启用防火墙，仅开放必要端口
- **HTTPS**：始终使用 HTTPS 传输数据（参考 [部署文档](docs/DEPLOYMENT.md) 中的 Nginx + Let's Encrypt 配置）
- **数据加密**：启用配置中的 `data_encryption: true` 选项
- **会话隔离**：多用户场景下确保 `session_isolation: true`
- **敏感操作确认**：保持 `sensitive_confirm: true` 和 `require_approval: true`
- **定期更新**：及时更新 ShuyuanCore 和依赖包到最新版本
- **审计日志**：定期检查 `audit_logs` 表和 `data/logs/audit.log`

---

## 已知安全机制

ShuyuanCore 内置 14 层安全防线：

1. 用户认证和权限分级
2. 危险命令审批（`/approve`）
3. 执行沙箱隔离（Docker 默认）
4. 行为审计日志
5. 供应链安全（技能安装前扫描）
6. 数据加密存储
7. 网络访问白名单
8. 隐私脱敏（手机号、身份证、银行卡）
9. 多用户会话隔离
10. 操作回滚（文件级快照）
11. 速率限制
12. 敏感操作二次确认
13. 模型输出过滤
14. 细粒度权限配置

---

## 安全相关配置

以下配置项与安全相关，部署前应仔细审查：

```yaml
security:
  require_approval: true        # 危险命令审批
  sandbox: docker               # 执行沙箱
  audit_log: true               # 审计日志
  data_encryption: true         # 数据加密
  network_isolation: true       # 网络隔离
  privacy_desensitize: true     # 隐私脱敏
  session_isolation: true       # 会话隔离
  operation_rollback: true      # 操作回滚
  rate_limit: true              # 速率限制
  sensitive_confirm: true       # 敏感操作确认
  output_filter: true           # 输出过滤
  permission_grading: true      # 权限分级
```

---

*最后更新：2026-05-29*
