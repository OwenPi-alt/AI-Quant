# AI-Quant Runbook

## 一、Cloudflare DNS 设置（DNS only + Caddy 自动 HTTPS）

域名托管在 Cloudflare，**仅做 DNS 解析**，不启用 Cloudflare 代理。LA 是公网入口，证书由 LA 上的 Caddy 通过 Let's Encrypt 自动申请。

在 Cloudflare 控制台建一条 A 记录：

```
Type:    A
Name:    quant         (或你的子域名)
IPv4:    <LA 公网 IP>
Proxy:   DNS only      ← 必须是灰云
TTL:     Auto
```

Cloudflare 的 SSL/TLS 模式（自动/Flexible/Full/Full Strict）在 DNS only 下**不生效**，因为 Cloudflare 不在请求路径上。

确认 DNS 解析正确：

```bash
dig +short quant.example.com
# 必须返回 LA 公网 IP，不是 Cloudflare 节点 IP（如 104.x / 172.x）
```

Caddy 启动后会自动通过 Let's Encrypt 完成 HTTP-01 验证并签发证书。**前提**：

- LA 公网 80/443 必须从 internet 可达（ufw 已经 allow）
- LA 域名解析必须正确（上面 dig 命令验证）
- Let's Encrypt 速率限制：每个域名每周最多 50 证书；自动续期不会触及

**未来如果想隐藏源 IP / 加 Cloudflare WAF**：见本文档"附录 A：切到 Cloudflare Proxied"。

## 二、Tokyo 部署

```bash
sudo bash scripts/bootstrap-tokyo.sh
cp .env.example .env
```

`.env` 必填项：

| 变量 | 说明 |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 24`；同步 `DATABASE_URL` / `SPRING_DATASOURCE_PASSWORD` |
| `API_AUTH_TOKEN` | `openssl rand -hex 32`；**Tokyo 和 LA 必须一致** |
| `APPROVAL_OPERATORS` | 默认 `alex`，单作者一人 |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin |
| `TAILSCALE_AUTHKEY` | Tailscale 后台生成的一次性 key |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 通知通道 |
| `LLM_API_KEY` | 当前 agent 是 mock，可留空 |

保持：

```text
TRADING_MODE=PAPER_ONLY
LIVE_TRADING_ENABLED=false
API_AUTH_ENABLED=true
POLYMARKET_MODE=OBSERVE_ONLY
```

启动：

```bash
bash scripts/deploy-tokyo.sh
```

`deploy-tokyo.sh` 会自动：

1. `tailscale up` 加入 Tailnet
2. `tailscale ip -4` 取本机 Tailscale IP
3. `export TOKYO_TAILSCALE_IP=100.x.y.z`
4. `docker compose up -d --build`，control-api 和 grafana 只绑到 `100.x.y.z:8080` / `100.x.y.z:3000`

Flyway 首次启动执行 V001/V002/V003 三个迁移。启动后看启动审计：

```bash
docker logs aiq-control-api 2>&1 | grep "READY" -A 30
```

期望：

```
api_auth              : ENABLED token_len=64
approval_operators    : [alex] (count=1)
polymarket_mode       : OBSERVE_ONLY
```

若 `api_auth: ENABLED_BUT_TOKEN_EMPTY` 或 `DISABLED`，立即停服修 `.env`。

## 三、LA 部署

```bash
sudo bash scripts/bootstrap-la.sh
cp .env.example .env
```

LA 的 `.env` 必填：

- `LA_PUBLIC_HOST` = 你的 Cloudflare 解析的域名
- `TAILSCALE_AUTHKEY`
- `TAILSCALE_HOSTNAME_TOKYO` = `ai-quant-tokyo`
- `API_AUTH_TOKEN` = **与 Tokyo 完全一致**
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`

启动：

```bash
bash scripts/deploy-la.sh
```

Caddy 在 1-2 分钟内自动签发证书。看进度：

```bash
docker logs aiq-caddy 2>&1 | grep -iE 'certificate|acme|ready'
```

期望看到：

```
certificate obtained successfully ... example.com
```

## 四、健康检查

```bash
# 公网访问（任何浏览器/curl，证书已 Let's Encrypt）
curl https://quant.example.com/health
# expect: 200, body 包含 {"status":"UP", "time":"..."}

# 公网访问 /api/* 必须 403（设计如此）
curl -i https://quant.example.com/api/v1/risk/status
# expect: HTTP/2 403, body: forbidden

# Tailscale 客户端访问（你本机 tailscale up 后）
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://ai-quant-tokyo:8080/api/v1/dashboard/summary

curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://ai-quant-tokyo:8080/api/v1/risk/status

# 容器状态
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env ps
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env logs -f collector-worker
```

## 五、单作者审批流

Telegram 收到通知后，从你本机（已经 `tailscale up` 加入 Tailnet）：

```bash
export API_AUTH_TOKEN=...       # 与 .env 一致
export DECISION_ID=...
export CODE=123456

curl -X POST http://ai-quant-tokyo:8080/api/v1/approvals/confirm \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"decisionId\":\"$DECISION_ID\",\"approvalCode\":\"$CODE\",\"approvedBy\":\"alex\"}"
```

约束：

- `approvedBy` 必须在 `APPROVAL_OPERATORS` 列表（默认仅 `alex`）
- `approvalCode` 在 `APPROVAL_TTL_MINUTES`（默认 10 分钟）内有效
- Redis SETNX 对同一 decision 15 分钟内只接受一次 confirm；重试需 `docker exec aiq-redis redis-cli DEL approval:confirm:$DECISION_ID`
- 二次风控会在 paper-broker 下单前重跑（含 entry 偏离检查）

确认后 `paper-broker` 在 20 秒轮询内调 `/api/v1/orders/paper`，`position-keeper` 每 60 秒盯 TP/SL。

## 六、端口与 ACL

| 端口 | 监听 | 用途 | 谁可访问 |
|---|---|---|---|
| LA `80/443` | docker eth0 0.0.0.0 | Caddy + Let's Encrypt | 公网（必须可达） |
| LA `22` | sshd 0.0.0.0 | SSH | 你自己（强烈建议 fail2ban + key-only） |
| Tokyo `8080` | docker `${TOKYO_TAILSCALE_IP}:8080` | control-api | 仅 Tailnet |
| Tokyo `3000` | docker `${TOKYO_TAILSCALE_IP}:3000` | Grafana | 仅 Tailnet |
| Tokyo eth0 `80/443` | (无 listener) | — | 公网 ufw 允许但无服务 |
| Postgres / Redis | docker 内网 | — | 仅 `aiq` docker network |

**重要：因为 Cloudflare 不代理，LA 公网 IP 直接暴露给所有 dig 你域名的人**。务必：

- LA SSH 改 key-only，禁用密码登录：`/etc/ssh/sshd_config` 设 `PasswordAuthentication no`
- 装 fail2ban 防 SSH 暴力（bootstrap-la.sh 已包含）

确认 Tokyo ufw：

```bash
sudo ufw status verbose
# 期望：
#   80/tcp                  ALLOW IN    Anywhere
#   443/tcp                 ALLOW IN    Anywhere
#   8080/tcp                DENY IN     Anywhere
#   3000/tcp                DENY IN     Anywhere
#   8080/tcp on tailscale0  ALLOW IN    Anywhere
#   3000/tcp on tailscale0  ALLOW IN    Anywhere
```

确认 docker 端口绑定（Tokyo）：

```bash
docker ps --format '{{.Names}}: {{.Ports}}' | grep -E 'control-api|grafana'
# 期望：
#   aiq-control-api: 100.x.y.z:8080->8080/tcp
#   aiq-grafana:     100.x.y.z:3000->3000/tcp
# 如果看到 0.0.0.0:8080，立即停服 — TOKYO_TAILSCALE_IP 没注入成功
```

## 七、备份

`backup-worker` 每日生成本地 `backups/ai_quant_*.sql.gz`，保留 14 天。

R2 同步在 host cron（不嵌进镜像）：

```bash
# /etc/cron.daily/aiq-r2-sync
aws --endpoint-url="$CLOUDFLARE_R2_ENDPOINT" s3 cp \
  /var/lib/aiquant/backups/ s3://ai-quant-backups/ --recursive --exclude '*' --include 'ai_quant_*.sql.gz'
```

每月做一次恢复演练：

```bash
gunzip -c backups/ai_quant_20260601T000000Z.sql.gz | \
  docker exec -i aiq-postgres psql -U ai_quant -d ai_quant_restore_test
```

## 八、关停 / 切实盘前 sanity-check

```bash
# 实盘开关
grep -E 'TRADING_MODE|LIVE_TRADING_ENABLED|POLYMARKET_MODE' .env
# 必须为：
#   TRADING_MODE=PAPER_ONLY
#   LIVE_TRADING_ENABLED=false
#   POLYMARKET_MODE=OBSERVE_ONLY

# 风控越权事件（理应为 0）
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT event_type, COUNT(*) FROM risk_event WHERE created_at > now() - interval '7 days' GROUP BY event_type;"

# 所有订单都应该是 PAPER_ONLY 模式
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT mode, COUNT(*) FROM trade_order GROUP BY mode;"
```

进入小资金实盘前必须逐项过 [docs/live-readiness-checklist.md](live-readiness-checklist.md)。任何异常立即：

```bash
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env stop \
  control-api paper-broker position-keeper agent-worker
```

## 九、常见排障

| 现象 | 原因 | 处置 |
|---|---|---|
| `control-api` exit 1，日志报 `CREATE EXTENSION vector` 失败 | Postgres 镜像未带 pgvector | `docker pull timescale/timescaledb-ha:pg16-all` 确认 tag，删卷重启 |
| Caddy 日志 `acme: certificate request failed` | LA 公网 80 不可达 / dig 解析不正确 / 速率限制 | `curl -I http://quant.example.com/` 自测；`dig +short` 验证 IP；查 letsencrypt 速率 |
| `deploy-tokyo.sh` 报 `Could not determine Tailscale IPv4` | tailscale 未启动 | `sudo tailscale up --auth-key=...`，`tailscale ip -4` 确认有 100.x |
| `docker ps` 看到 `0.0.0.0:8080->8080` 不是 `100.x.y.z:8080->8080` | `TOKYO_TAILSCALE_IP` 没 export | 重跑 `bash scripts/deploy-tokyo.sh`；多 IP 时强制 `TOKYO_TAILSCALE_IP=100.x.y.z` |
| 所有 `/api/*` 返回 401 | `API_AUTH_TOKEN` 不一致 / 没传 | 同步 Tokyo 和 LA 的 `.env`，`up -d --force-recreate` |
| 启动日志 `api_auth: ENABLED_BUT_TOKEN_EMPTY` | `.env` 漏填 `API_AUTH_TOKEN` | 填入后 `up -d --force-recreate control-api` |
| `approval invalid` 总返回 | `approvedBy` 不在 `APPROVAL_OPERATORS`，或 Redis SETNX 已锁 | 检查 ID；`docker exec aiq-redis redis-cli DEL approval:confirm:<decision_id>` |
| `paper-broker` 持续 `ALREADY_FILLED` | 该 decision 已下过单（幂等保护正常） | 不需处理 |
| Polymarket 突然不再写 `market_snapshot` | geoblock 命中 | `risk_event` 表中应有 `GEOBLOCK` 行；合规预期，**不要绕过** |
| LA SSH 被刷 | 源 IP 暴露（DNS only 必然） | `sudo fail2ban-client status sshd` 查封禁；改非 22 端口；关闭密码登录 |

## 附录 A：可选 — 切换到 Cloudflare Proxied 隐藏源 IP

当 DDoS 或扫描频率上来时，可考虑切到 Cloudflare proxied：

1. Cloudflare > DNS：把 A 记录的 Proxy 切到 **Proxied**（橙云）。
2. Cloudflare > SSL/TLS > Origin Server > **Create Certificate**：
   - Private key type: RSA
   - Hostnames: `quant.example.com`、`*.quant.example.com`
   - Validity: 15 years
   - 下载 PEM 和 Key
3. 放到 `deploy/la/caddy-tls/origin.pem` 和 `origin.key`。
4. 编辑 `deploy/caddy/Caddyfile`，取消注释：
   ```
   tls /etc/caddy/tls/origin.pem /etc/caddy/tls/origin.key
   ```
5. Cloudflare > SSL/TLS > Overview：mode 设为 **Full (strict)**。
6. 重启 caddy：`docker compose -f deploy/la/docker-compose.yml --env-file .env up -d --force-recreate caddy`

切换后：

- Caddy 看到的源 IP 是 Cloudflare 节点（不在 100.64.0.0/10）
- `/api/*` 公网照样返回 403（设计如此，不依赖 Cloudflare 头）
- 你从 Tailscale 客户端直连 `http://ai-quant-tokyo:8080` 仍然能工作，因为完全绕过 Cloudflare
