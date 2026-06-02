# AI-Quant

个人小资金 AI 自学习量化交易系统 MVP。

目标路径：

1. 1 周内部署完成。
2. 先跑模拟盘与观察模式。
3. 连续稳定运行后，再按 checklist 开启极小资金、人工确认、低风险实盘。

## 核心原则

- 默认 `PAPER_ONLY`，实盘默认关闭。
- Agent 只给结构化建议和复盘归因，**不能直接控制资金**。
- 所有写操作（创建 decision / 审批 / 下单）都必须带 `API_AUTH_TOKEN`（Bearer）。
- 审批操作必须由 `APPROVAL_OPERATORS` 白名单内的人完成（默认仅作者一人）。
- 真实密钥只允许放在 `.env`、Docker secrets 或服务器环境变量中，禁止写入代码、文档、提示词或 GitHub。
- Polymarket 初期只观察和模拟；必须遵守地区限制，**绝不**用 VPS/VPN 绕过。

## 拓扑

```
  浏览器 / Telegram webhook
        │
        ▼  HTTPS (Caddy 自动 Let's Encrypt 证书)
   ┌─────────────┐
   │  LA Caddy   │  公网 80/443；/api/* 仅 Tailscale 客户端可达
   └──────┬──────┘
          │  Tailscale (WireGuard)
          ▼
   ┌─────────────┐
   │  Tokyo      │  eth0 公网只开 22/80/443（80/443 无服务监听）
   │  control-api│  8080/3000 仅绑 tailscale0 IP
   │  workers ×7 │
   │  postgres   │  仅 docker 内网
   │  redis      │
   │  grafana    │
   └─────────────┘
        │
        └─► Binance / Hyperliquid / Polymarket / LLM
```

**网络说明**：
- Cloudflare 只做 DNS 解析（DNS only / 灰云），不在请求路径上。
- LA 公网 80/443 必须真正可达，Caddy 直接从 Let's Encrypt 申请证书。
- Tokyo 的 8080/3000 通过 Docker 端口绑定到 Tailscale 接口 IP，公网不可见。

## 部署顺序（单作者 · Cloudflare 仅 DNS 解析）

### 步骤 1：Cloudflare DNS

在 Cloudflare 控制台为你的域名建一条 A 记录：

```
Type:  A
Name:  quant   (or your subdomain)
IPv4:  <LA 服务器公网 IP>
Proxy: DNS only   ← 关键：必须是灰云
TTL:   Auto
```

确认：

```bash
dig +short quant.example.com    # 应直接返回 LA 公网 IP，不是 Cloudflare 节点
```

### 步骤 2：Tokyo VPS（东京）

```bash
sudo bash scripts/bootstrap-tokyo.sh        # 装 docker / tailscale / ufw
cp .env.example .env
# 在 .env 中填入：
#   POSTGRES_PASSWORD     openssl rand -hex 24
#   API_AUTH_TOKEN        openssl rand -hex 32  （记下来，LA 端也要用）
#   APPROVAL_OPERATORS    alex                  （或你的标识，作者一人）
#   GRAFANA_ADMIN_PASSWORD
#   TAILSCALE_AUTHKEY     从 Tailscale 后台一次性生成
#   TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
#   LLM_API_KEY           可留空（agent 是 mock）
bash scripts/deploy-tokyo.sh                 # 自动检测 Tailscale IP，绑定到 8080/3000
```

`deploy-tokyo.sh` 会 fail-fast 如果 Tailscale 没连上。

### 步骤 3：LA VPS（洛杉矶）

```bash
sudo bash scripts/bootstrap-la.sh
cp .env.example .env
# LA 的 .env 必须填：
#   LA_PUBLIC_HOST        quant.example.com  （与 Cloudflare DNS 一致）
#   TAILSCALE_AUTHKEY
#   TAILSCALE_HOSTNAME_TOKYO   ai-quant-tokyo
#   API_AUTH_TOKEN        必须与 Tokyo 完全一致
#   TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
bash scripts/deploy-la.sh
```

Caddy 启动后会在 1-2 分钟内自动申请 Let's Encrypt 证书。

### 步骤 4：验证

```bash
# 从公网验证（任何浏览器）
curl https://quant.example.com/health          # 200 OK + JSON
curl -i https://quant.example.com/api/v1/risk/status   # 403 forbidden（设计如此）

# 从 LA 直连 Tokyo（Tailscale 网内）
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://ai-quant-tokyo:8080/api/v1/risk/status   # 200

# 看 control-api 启动审计日志
docker logs aiq-control-api 2>&1 | grep "READY" -A 30
# 期望看到：
#   api_auth              : ENABLED token_len=64
#   approval_operators    : [alex] (count=1)
#   polymarket_mode       : OBSERVE_ONLY
```

## 自学习闭环

每次 signal → agent → 审批 → 模拟盘 → 24h/48h/7d 自动复盘 → `experience_memory`（pgvector）。

agent 处理下一个 signal 时：

- 用 EmbeddingProvider 把"当前 market + symbol + features"转向量
- 在 `wiki_entry`（15 条种子 + 你新增的）和 `experience_memory`（过往复盘）里 cosine 召回 top-5
- 把 wiki + experience 注入 `agent_json.wiki_hints[]` 和 `experience_hints[]`
- Telegram 通知里显示前 3 条 wiki 标题，让你审批前一眼看到

embedding provider 可切换：默认 `deterministic`（SHA-256，零成本）；切到 `openai_compat` 即用 DeepSeek/OpenAI/Tongyi/Ollama 的 `/v1/embeddings`。详见 [docs/wiki.md](docs/wiki.md)。

## 详细文档

- [docs/runbook.md](docs/runbook.md) — 部署、健康检查、Cloudflare 配置、排障
- [docs/wiki.md](docs/wiki.md) — 向量库 / wiki 召回 / EmbeddingProvider 切换
- [docs/live-readiness-checklist.md](docs/live-readiness-checklist.md) — 进入小资金实盘前必检清单
- [docs/official-links.md](docs/official-links.md) — 已核对的官方 API 链接
