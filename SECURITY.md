# Security Policy

如果你发现安全问题，请不要在公开 Issue 中披露完整细节。建议通过私有渠道联系维护者，并提供：

- 影响范围
- 复现步骤
- 涉及接口或文件
- 建议修复方式

## 数据安全原则

- 服务端接口不得返回完整手机号、密码、Token、Cookie 等敏感信息。
- 前端脱敏仅用于展示，不能替代后端脱敏。
- `deploy.env`、`backend/.env`、`web-client/.env*` 等本地配置不得提交到 Git。
- 生产环境必须修改 `JWT_SECRET_KEY`、`POSTGRES_PASSWORD`，并限制 `CORS_ORIGINS`。
