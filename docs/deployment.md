# 部署 Step-by-Step

按顺序执行，**每一步都要等返回值符合预期再继续**。中途任何异常**立即停**，按"排障"那一节查。

预计总时长：首次 ~40-60 分钟（含拉镜像）；熟练后 ~15 分钟。

---

## 0. 准备工作（部署前 1 天）

| 项 | 操作 | 检验 |
|---|---|---|
| Tokyo VPS | 4C/8G/200GB SSD，Ubuntu 22.04 或 24.04 | `ssh root@<tokyo_ip> 'cat /etc/os-release'` |
| LA VPS | 2C/6G+，同上 | 同上 |
| Tailscale 账号 | 后台启用 **MagicDNS**（DNS > MagicDNS 开关绿色）；生成一次性 auth key（24h，prefix `tskey-auth-...`） | 后台能看到 key |
| Cloudflare DNS | A 记录 `quant.example.com` → LA 公网 IP；**Proxy = DNS only（灰云）** | `dig +short quant.example.com` 返回 LA 公网 IP |
| 解析 TTL | 5min（方便切换） | — |
| Telegram Bot | @BotFather 新建 bot，记 token；找 chat_id（`@userinfobot`） | `curl https://api.telegram.org/bot$TOKEN/getMe` |
| Git clone | LA 和 Tokyo 各 `git clone <repo> /opt/aiquant` | `cd /opt/aiquant && git status` |

---

## 1. Tokyo VPS 部署（先做 Tokyo，再做 LA）

### 1.1 主机环境

```bash
ssh root@<tokyo_ip>
cd /opt/aiquant
sudo bash scripts/bootstrap-tokyo.sh
```

**等输出**：`Tokyo bootstrap done. Next: copy repo, create .env, run scripts/deploy-tokyo.sh`

如果有 `E: ` 开头的 apt 错误，先解决。

**SSH 加固**：bootstrap 会打印提示。**在第二个 SSH 窗口**验证 pubkey 登录能成功，再去 `/etc/ssh/sshd_config` 关 `PasswordAuthentication`，systemctl restart ssh。**不要在唯一窗口里做**。

### 1.2 生成 .env

```bash
cp .env.example .env

# 3 个关键秘钥（记到本机记事本）
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
echo "API_AUTH_TOKEN=$(openssl rand -hex 32)"
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 16)"

# 编辑 .env，把上面 3 个值粘进去，同时填其他必填项
vi .env
```

**必填**（核对一遍）：

- `POSTGRES_PASSWORD` / `DATABASE_URL` 中的密码 / `SPRING_DATASOURCE_PASSWORD` — **三处必须一致**
- `API_AUTH_TOKEN` — 抄到记事本，LA 端要用同一个值
- `APPROVAL_OPERATORS=alex`（你的 ID）
- `GRAFANA_ADMIN_PASSWORD`
- `TAILSCALE_AUTHKEY`
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `LA_PUBLIC_HOST=quant.example.com`

**必保持不动**：

```
TRADING_MODE=PAPER_ONLY
LIVE_TRADING_ENABLED=false
API_AUTH_ENABLED=true
POLYMARKET_MODE=OBSERVE_ONLY
EMBEDDING_PROVIDER=deterministic
```

### 1.3 启动

```bash
bash scripts/deploy-tokyo.sh
```

首次拉镜像 5-10 分钟。

### 1.4 立即核对（7 项，每条必 PASS）

```bash
# (1) ports 必须绑 Tailscale IP（不能 0.0.0.0）
docker ps --format '{{.Names}}: {{.Ports}}' | grep -E 'control-api|grafana'
# 期望：
#   aiq-control-api: 100.x.y.z:8080->8080/tcp
#   aiq-grafana:     100.x.y.z:3000->3000/tcp
# 看到 0.0.0.0 或 127.0.0.1 → 立即停服查 TOKYO_TAILSCALE_IP

# (2) 容器都 healthy
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env ps
# postgres / redis / control-api 必须 Up (healthy)
# 7 个 worker 必须 Up

# (3) Flyway 4 个迁移都跑了
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
# 期望 4 行，success=t

# (4) 15 条 wiki seed
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT category, COUNT(*) FROM wiki_entry GROUP BY category ORDER BY category;"
# 期望合计 15 行

# (5) StartupAuditor 输出正常
docker logs aiq-control-api 2>&1 | grep "control-api READY" -A 25
# 必须看到：
#   api_auth              : ENABLED token_len=64
#   approval_operators    : [alex] (count=1)
#   polymarket_mode       : OBSERVE_ONLY
# 不能看到 ENABLED_BUT_TOKEN_EMPTY / DISABLED

# (6) ufw 规则正确
sudo ufw status verbose | grep -E '8080|3000'
# 期望：
#   8080/tcp                DENY IN     Anywhere
#   3000/tcp                DENY IN     Anywhere
#   8080/tcp on tailscale0  ALLOW IN    Anywhere
#   3000/tcp on tailscale0  ALLOW IN    Anywhere

# (7) 公网扫描 Tokyo 应该看不到 8080/3000
# 在本机（非 Tokyo）跑：
nmap -p 8080,3000 -Pn <Tokyo 公网 IP>
# 期望：8080/tcp closed/filtered, 3000/tcp closed/filtered
```

**任何一项失败 → 立即停**：`docker compose -f deploy/tokyo/docker-compose.yml --env-file .env down`，查"排障"。

---

## 2. LA VPS 部署

### 2.1 主机环境

```bash
ssh root@<la_ip>
cd /opt/aiquant
sudo bash scripts/bootstrap-la.sh
```

### 2.2 生成 .env

```bash
cp .env.example .env
vi .env
```

**必须与 Tokyo 完全一致的字段**：

```
API_AUTH_TOKEN=<从 Tokyo 抄过来，确保两端字节一致>
TELEGRAM_BOT_TOKEN=<同 Tokyo>
TELEGRAM_CHAT_ID=<同 Tokyo>
LA_PUBLIC_HOST=quant.example.com
TAILSCALE_HOSTNAME_TOKYO=ai-quant-tokyo
APPROVAL_OPERATORS=alex
```

**LA 独有**：

```
TAILSCALE_AUTHKEY=<新生成一个，不要复用 Tokyo>
```

数据库相关字段（POSTGRES_*）在 LA 不用，留占位即可。

### 2.3 启动

```bash
bash scripts/deploy-la.sh
```

1-3 分钟。

### 2.4 立即核对（4 项）

```bash
# (1) Caddy 1-2 分钟内拿到 Let's Encrypt 证书
docker logs aiq-caddy 2>&1 | grep -iE 'certificate.*obtained|cert.*ok|certificate magic'
# 期望看到：certificate obtained successfully ...quant.example.com

# (2) DNS 解析（关键，BLOCKER-3 防护）
docker exec aiq-la-notifier nslookup ai-quant-tokyo
# 期望返回 100.x.y.z
# 如果 NXDOMAIN → 检查 docker-compose dns 配置 + Tailscale MagicDNS 开关

# (3) notifier 心跳
docker logs aiq-la-notifier 2>&1 | tail -10
# 期望看到 "[AI-Quant] LA notifier online" 或 "control api health=..."
# 如果反复 "control api health check failed" → 5 分钟后再 docker logs，可能是首次握手延迟

# (4) 公网访问
curl -i https://quant.example.com/health
# 期望：HTTP/2 200, body 含 {"status":"UP"}
curl -i https://quant.example.com/api/v1/risk/status
# 期望：HTTP/2 403, body "forbidden"（设计如此）
```

---

## 3. 端到端验证（你本机做）

**前提**：你本机装 Tailscale 客户端、登录同账号。

```bash
# (1) MagicDNS 解析
nslookup ai-quant-tokyo
# 应返回 100.x.y.z

# (2) 直连 Tokyo（带 Bearer）
export API_AUTH_TOKEN=<.env 里的>
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://ai-quant-tokyo:8080/api/v1/dashboard/summary
# 期望 JSON：{"success":true,"data":{"account":{"equityUsd":1000,...},...}}

curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://ai-quant-tokyo:8080/api/v1/risk/status
# 期望：trading_mode=PAPER_ONLY, polymarket_mode=OBSERVE_ONLY

# (3) Grafana
浏览器 → http://ai-quant-tokyo:3000
登录 admin / <GRAFANA_ADMIN_PASSWORD>
Dashboards → AI-Quant → Overview 看到 4 个 stat panel
```

---

## 4. 跑通首个交易闭环（30 分钟内）

部署后系统自动跑：

| 时间窗 | 自动动作 |
|---|---|
| 0-5 min | collector-worker 拉 Binance/HL/PM 行情，写 market_snapshot |
| 5-30 min | strategy-worker 每 5 分钟扫，产 trade_signal |
| signal 后 30s | agent-worker 召回 wiki + experience → 写 decision_log → 申请 approval → Telegram 通知 |
| 你审批 | curl `/api/v1/approvals/confirm` |
| 审批后 20s | paper-broker 二次风控 → 写 trade_order + trade_position + 3 个 review_task |
| +24/48/168h | review-worker 算 MFE/MAE，写 review_result + experience_memory + 复盘 Telegram |

### 检查 collector 拉数据

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT source, COUNT(*), MAX(created_at) FROM market_snapshot GROUP BY source;"
# 5 分钟后各 source 都应 >= 5 行
```

### 检查 wiki backfill

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS filled, COUNT(*) FROM wiki_entry;"
# 第 1 个 signal 处理后期望 filled=15
```

### 审批 Telegram 通知里的 decision

```bash
# 本机（已加 Tailnet）
export API_AUTH_TOKEN=<.env 里的>
export DECISION_ID=<通知里的>
export CODE=<通知里的 6 位数字>

curl -X POST http://ai-quant-tokyo:8080/api/v1/approvals/confirm \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"decisionId\":\"$DECISION_ID\",\"approvalCode\":\"$CODE\",\"approvedBy\":\"alex\"}"
# 期望：{"success":true,"data":{"approvalId":"...","status":"APPROVED",...}}
```

20 秒后看订单：

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT decision_id, symbol, side, qty, status, mode FROM trade_order ORDER BY created_at DESC LIMIT 3;"
# 期望 status=PAPER_FILLED, mode=PAPER_ONLY
```

---

## 5. 部署注意事项（不能犯的错）

| # | 错误 | 后果 | 怎么防 |
|---|---|---|---|
| 1 | `API_AUTH_TOKEN` Tokyo 和 LA 不一致 | LA 容器全部 401 刷日志 | 部署前 diff 两端 .env：`diff <(ssh tokyo "grep API_AUTH_TOKEN /opt/aiquant/.env") <(grep API_AUTH_TOKEN .env)` |
| 2 | `.env` 里 token 末尾有空格/换行 | Java 端有 trim 兜底 ✓ Python 端也有 ✓ | 已修，无需特别注意 |
| 3 | 没经过 `deploy-tokyo.sh` 直接跑 `docker compose up` | port 绑到 127.0.0.1（fail-secure），LA 连不上 | 永远用 `bash scripts/deploy-tokyo.sh` |
| 4 | `LIVE_TRADING_ENABLED=true` | 真实下单 | 前 7 天保持 false |
| 5 | `POLYMARKET_MODE` 不是 `OBSERVE_ONLY` | 风控会拒，但合规风险 | 不要改 |
| 6 | MagicDNS 没开 | LA 容器解析不到 ai-quant-tokyo | Tailscale 后台 DNS > MagicDNS 必须绿色 |
| 7 | Cloudflare 切到 Proxied | Caddy ACME 失败拿不到证书 | 保持 DNS only / 灰云 |
| 8 | SSH 没关密码登录 | LA 公网暴露，几小时被刷 | bootstrap 后立即关，fail2ban 只是缓冲 |
| 9 | `EMBEDDING_PROVIDER=openai_compat` 但 `EMBEDDING_API_KEY` 空 | 自动 fallback 到 deterministic ✓ | 不影响部署 |
| 10 | 重启 VPS 后 `TOKYO_TAILSCALE_IP` 不一致 | docker daemon 自动用旧 spec（IP 已写死） | 一般不会变；若变则重跑 deploy-tokyo.sh |

### 部署后**立即**核对（每条必 PASS）

```bash
# Tokyo 上跑
docker ps --format '{{.Names}}: {{.Ports}}' | grep -E '8080|3000'
# 必须看到 100.x.y.z:8080，不能 0.0.0.0 也不能 127.0.0.1

curl -i https://quant.example.com/api/v1/risk/status      # 必须 403
curl -H "Authorization: Bearer $API_AUTH_TOKEN" http://ai-quant-tokyo:8080/api/v1/risk/status  # 必须 200

docker logs aiq-control-api | grep "READY" -A 20 | grep -E "TOKEN_EMPTY|DISABLED"  # 必须为空（无匹配）

sudo ufw status | grep -E '8080|3000'      # 必须看到 DENY 公网, ALLOW tailscale0

nmap -p 8080,3000,5432,6379 -Pn <Tokyo 公网 IP>  # 全部 closed / filtered
```

---

## 6. 排障对照表

| 现象 | 直接定位 | 怎么修 |
|---|---|---|
| `deploy-tokyo.sh` 卡 "Could not determine Tailscale IPv4" | tailscale 没起 | `sudo tailscale up --auth-key=... --accept-dns=true`，`tailscale ip -4` 验证 |
| `docker compose up` 报 `invalid port` 或绑到 `127.0.0.1` | `TOKYO_TAILSCALE_IP` 未注入 | 用 `bash scripts/deploy-tokyo.sh` 而不是直接 `docker compose` |
| `docker ps` 看到 `0.0.0.0:8080` | export 失败 | `export TOKYO_TAILSCALE_IP=$(tailscale ip -4 \| head -1)`，再 `docker compose ... up -d --force-recreate control-api grafana` |
| Postgres exit 1 `CREATE EXTENSION vector` 失败 | 镜像 tag 错 | 确认 `timescale/timescaledb-ha:pg16-all`；删 postgres_data 卷重启 |
| Flyway 启动后报 `Migration V004 failed and was not repaired` | V004 已部分执行过 | 进 psql：`DELETE FROM flyway_schema_history WHERE version='004' AND success=false; UPDATE wiki_entry SET active=false WHERE source='manual';` 然后 `docker compose ... up -d --force-recreate control-api`（V004 ON CONFLICT 会跳过已有 title） |
| control-api 起来但 `api_auth: ENABLED_BUT_TOKEN_EMPTY` | `.env` 漏填 `API_AUTH_TOKEN` | 填上，`docker compose ... up -d --force-recreate control-api` |
| LA notifier 持续 "control api health check failed" | (1) DNS 解析失败 / (2) token 不一致 / (3) Tokyo 端口没绑对 | 1) `docker exec aiq-la-notifier nslookup ai-quant-tokyo`；2) `diff` 两端 token；3) Tokyo `docker ps` 看 ports |
| `nslookup ai-quant-tokyo` 在 LA 容器内 NXDOMAIN | docker dns 没生效 | 确认 `deploy/la/docker-compose.yml` 里 caddy/notifier 都有 `dns: [100.100.100.100, 1.1.1.1]`，重启容器 |
| Caddy 拿不到证书 (acme error) | LA 公网 80 不通 / DNS 解析错 / 速率限制 | `dig +short quant.example.com` 必须返回 LA 公网 IP；`curl http://quant.example.com/health` 公网 80 必须通 |
| 公网 `curl /api/*` 返回 200（应 403） | Caddyfile ACL 被破坏 | `cat deploy/caddy/Caddyfile` 检查；`docker logs aiq-caddy` |
| Telegram 没收到通知 | bot token / chat_id 错 | `curl https://api.telegram.org/bot$TOKEN/sendMessage -d chat_id=$ID -d text=test` 自测 |
| `/api/v1/approvals/confirm` 401 | 缺 Bearer 头 | 加 `-H "Authorization: Bearer $API_AUTH_TOKEN"` |
| approval 返回 `"approval invalid"` | (1) approvedBy 不在 allowlist / (2) Redis 锁 / (3) 过期 | 检查 approvedBy；`docker exec aiq-redis redis-cli DEL approval:confirm:$DECISION_ID`；看 expires_at |
| collector 不写 market_snapshot | 网络不通 / 交易所限流 | `docker exec aiq-collector-worker curl -I https://api.binance.com` |
| Polymarket 不写 snapshot | geoblock 命中（合规预期） | `risk_event` 表里应有 `GEOBLOCK` 行；**不要绕过** |

---

## 7. 一键回滚（30 分钟内确认有问题）

```bash
# Tokyo
cd /opt/aiquant
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env down
# 保留数据：down ; 完全清空：down -v（删卷，数据库会重建）

# LA
docker compose -f deploy/la/docker-compose.yml --env-file .env down
```

清空重来：

```bash
docker volume rm aiquant_postgres_data aiquant_redis_data aiquant_grafana_data
bash scripts/deploy-tokyo.sh   # Flyway 重新跑 V001-V004
```

---

## 8. 24h / 7d 检查

24h：

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT risk_status, COUNT(*) FROM decision_log WHERE created_at > now() - interval '24h' GROUP BY risk_status;
   SELECT status, mode, COUNT(*) FROM trade_order WHERE created_at > now() - interval '24h' GROUP BY status, mode;
   SELECT event_type, COUNT(*) FROM risk_event WHERE created_at > now() - interval '24h' GROUP BY event_type;
   SELECT category, title, use_count FROM wiki_entry ORDER BY use_count DESC LIMIT 10;"
```

7d：

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT window_name, COUNT(*) FROM review_result WHERE created_at > now() - interval '7d' GROUP BY window_name;
   SELECT COUNT(*) FROM experience_memory;
   SELECT created_at, equity_usd, daily_pnl_usd, weekly_pnl_usd, consecutive_losses
     FROM account_snapshot ORDER BY created_at DESC LIMIT 20;"
```

review 三个窗口都有数据 + experience_memory 累积 + account 曲线正常 → 可以**考虑**走 [docs/live-readiness-checklist.md](live-readiness-checklist.md) 进入小资金实盘。
