# Web 管理端

## 推荐配置方式

项目根目录有统一配置文件：

```bash
cd /Users/admin/Documents/ChromeNetWork
vim deploy.env
./scripts/apply-config.sh
```

脚本会自动生成本目录的 `.env` / `.env.production`，Web 端会读取：

```env
VITE_API_BASE=http://0.0.0.0:3088
```

本地开发：

```bash
npm install
npm run dev
```

默认监听：`0.0.0.0:3090`。

如果要让局域网其他设备访问，请在根目录 `deploy.env` 中把 `PUBLIC_API_BASE` 改成本机 IP，例如：

```env
PUBLIC_API_BASE=http://192.168.1.23:3088
PUBLIC_WEB_BASE=http://192.168.1.23:3090
```

然后重新执行：

```bash
./scripts/apply-config.sh
npm run dev
```
