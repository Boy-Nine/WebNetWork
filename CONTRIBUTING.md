# Contributing

感谢关注 API Capture。提交 PR 前建议先确认：

1. 执行 `./scripts/doctor.sh` 通过基础检查。
2. 前端改动执行 `npm --prefix web-client run build`。
3. 后端改动执行 `python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py`。
4. 不要提交本地配置、数据库数据、账号密码、Token、Cookie 或抓包中的敏感数据。

## 开发流程

```bash
cp deploy.env.example deploy.env
./scripts/apply-config.sh
docker compose up -d --build
```

Web 管理端默认地址：`http://localhost:3090`。

## 代码风格

- 后端保持路由、模型、解析工具分层。
- 前端优先复用统一样式变量，不在组件里写零散内联样式。
- 插件抓包逻辑尽量保持可回滚、可解释，避免污染目标页面运行环境。
