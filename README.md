# API Capture

> Chrome Side Panel 接口捕获插件 + FastAPI 解析后端 + React WebPC 数据管理平台。

API Capture 用于手动记录网页中的接口请求，按公共规则过滤/解析响应数据，并把结构化结果沉淀为可查询、可导出的标签数据表。

## Features

- Chrome MV3 Side Panel 插件，支持开始记录、实时预览、停止上报。
- 优先使用 Chrome Debugger / CDP Network 捕获请求，回退到 Fetch/XHR 注入拦截。
- 公共规则池：URL 匹配、Params 过滤、Response 列表路径、字段映射与字段清洗。
- 标签数据表：按标签落结构化数据，支持字段筛选、时间筛选、详情查看、Excel 导出。
- WebPC 管理端：接口明细、规则管理、标签数据、看板统计、个人中心。
- 后端数据隔离：接口数据、标签数据按当前登录用户隔离；公共规则仅创建人可编辑。
- 安全保护：后端响应手机号脱敏，本地配置文件不进入 Git。

## Screenshots

> 建议在正式开源前补充 2-3 张截图：WebPC 看板、规则编辑、插件侧边栏。

## Tech Stack

| Layer | Stack |
| --- | --- |
| Chrome Extension | Manifest V3, Side Panel, Chrome Debugger/CDP, Content Script |
| Backend | Python 3.11, FastAPI, SQLAlchemy, PostgreSQL JSONB, JWT |
| WebPC | React 18, TypeScript, Vite, Ant Design 5, Axios |
| Deployment | Docker Compose |

## Quick Start

```bash
git clone https://github.com/Boy-Nine/WebNetWork.git
cd WebNetWork
cp deploy.env.example deploy.env
./scripts/apply-config.sh
docker compose up -d --build
```

默认地址：

- WebPC: <http://localhost:3090>
- Backend: <http://localhost:3088>
- API Docs: <http://localhost:3088/docs>

如果你没有手动复制 `deploy.env`，执行 `./scripts/apply-config.sh` 时会自动从 `deploy.env.example` 生成一份。

## Chrome Extension

1. 打开 Chrome：`chrome://extensions/`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择项目里的 `chrome-extension/`
5. 登录插件后，在目标页面点击「开始记录」

> 如果要让其他设备访问本机服务，请把 `deploy.env` 中的 `PUBLIC_API_BASE` / `PUBLIC_WEB_BASE` 改成局域网 IP 或 HTTPS 域名，然后重新执行 `./scripts/apply-config.sh`。

## Configuration

主要配置在 `deploy.env`：

```env
PUBLIC_API_BASE=http://0.0.0.0:3088
PUBLIC_WEB_BASE=http://0.0.0.0:3090
BACKEND_PORT=3088
WEB_PORT=3090
POSTGRES_DB=webgrabber
POSTGRES_USER=webgrabber
POSTGRES_PASSWORD=change-me
JWT_SECRET_KEY=change-me-at-least-32-bytes
CORS_ORIGINS=*
```

生产环境必须修改：

- `JWT_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `CORS_ORIGINS`

## Useful Scripts

```bash
./scripts/apply-config.sh      # 根据 deploy.env 生成后端/Web/插件/Docker 配置
./scripts/doctor.sh            # 项目自检
./scripts/restart-web.sh       # 仅重建 WebPC
./scripts/repair-docker-mac.sh # 修复部分 macOS Docker CLI 问题
```

## Development

前端：

```bash
npm --prefix web-client install
npm --prefix web-client run dev
npm --prefix web-client run build
```

后端：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
```

整体：

```bash
./scripts/doctor.sh
docker compose up -d --build
```

## Security Notes

- 不要提交 `deploy.env`、`backend/.env`、`web-client/.env*`。
- 后端接口会对手机号等明显敏感字段做脱敏返回。
- 前端脱敏只用于展示，不能替代后端脱敏。
- 捕获到的请求体/响应体可能包含敏感数据，请按业务场景设置规则和数据保留策略。

详见 [SECURITY.md](./SECURITY.md)。

## Roadmap

- [ ] 增加单元测试与 CI
- [ ] 增加截图与在线 Demo 文档
- [ ] 支持多租户套餐/额度限制
- [ ] 支持规则版本管理与回滚
- [ ] 支持敏感字段配置化脱敏

## License

[MIT](./LICENSE)

## Membership / Commercialization

项目已内置会员基础能力：

- 免费版：基础捕获、基础查询、手写规则、少量导出。
- 专业版：自动生成规则、自动识别字段、cURL 导入、规则测试诊断、高级字段筛选、更大导出额度。
- 团队版：批量删除、团队级额度、更多规则/标签/导出上限。

后端会在关键接口强校验套餐能力和额度，不只依赖前端禁用按钮。

### 手动开通会员

生产环境请先配置管理密钥：

```env
MEMBERSHIP_ADMIN_KEY=replace-with-a-long-random-secret

# 微信支付 API v3 / Native 扫码支付
WECHAT_PAY_ENABLED=true
WECHAT_PAY_MERCHANT_ID=your_mch_id
WECHAT_PAY_API_KEY_V3=your_32_byte_api_v3_key
WECHAT_PAY_APP_ID=your_appid
# 本地开发可先写本机/内网穿透地址；上线前只改这里为公网 HTTPS 回调地址
WECHAT_PAY_NOTIFY_URL=http://localhost:3088/api/membership/wechat/notify
WECHAT_PAY_CERT_PATH=/app/backend/certs/apiclient_cert.pem
WECHAT_PAY_KEY_PATH=/app/backend/certs/apiclient_key.pem
# 可留空，后端会从 apiclient_cert.pem 自动读取商户证书序列号
WECHAT_PAY_MCH_SERIAL_NO=
# 生产建议配置微信支付平台证书并开启回调签名验签
WECHAT_PAY_PLATFORM_CERT_PATH=
WECHAT_PAY_VERIFY_NOTIFY_SIGNATURE=false
```

示例：给某个手机号开通 31 天专业版：

```bash
curl -X POST 'http://localhost:3088/api/membership/admin/grant' \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-Key: replace-with-a-long-random-secret' \
  -d '{"phone":"13734295322","plan":"pro","days":31}'
```

> `/api/membership/checkout` 已接入微信支付 API v3 Native 下单，返回 `codeUrl` 后前端展示微信扫码二维码。微信回调 `/api/membership/wechat/notify` 解密成功、校验订单号与金额后自动更新订单为 `paid` 并开通会员。

### 会员订单闭环

当前已支持“创建订单 → 管理员确认 → 自动开通会员”的基础闭环：

1. 用户在 WebPC 会员弹窗点击“创建订单”。
2. 后端生成/复用 10 分钟内有效的 `membership_orders` 待支付订单，并调用微信 Native 下单返回二维码链接。
3. 管理员确认订单：

```bash
# 微信支付成功后会自动回调，无需管理员确认。
# 本地联调时注意：微信服务器无法访问 localhost，需要使用 ngrok/frp 等内网穿透地址作为 WECHAT_PAY_NOTIFY_URL。
```

4. 订单变为 `paid`，系统自动更新用户会员套餐和到期时间。

管理员也可以查询用户和订单：

```bash
curl 'http://localhost:3088/api/membership/admin/users' -H 'X-Admin-Key: replace-with-a-long-random-secret'
curl 'http://localhost:3088/api/membership/admin/orders?status=pending' -H 'X-Admin-Key: replace-with-a-long-random-secret'
```
