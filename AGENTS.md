# AI-Quant Agent Instructions

本仓库是个人小资金 AI 自学习量化交易系统，默认目标是模拟盘与观察模式。

## 固定安全约束

- 默认 `PAPER_ONLY`。
- 禁止把真实 API key、私钥、Telegram token、R2 secret 写入代码、文档、提示词或 GitHub。
- Agent 只能生成结构化交易建议、复盘归因、经验总结、规则候选。
- 资金相关动作必须经过代码硬风控和人工确认。
- 无止损、未确认、风控失败、JSON 不合规、confidence 不足、RR 不足，一律禁止下单。
- Polymarket 初期只观察和模拟，必须遵守地区限制，禁止用 VPS/VPN 绕过。

## 技术栈

- Java 21 + Spring Boot 3 控制 API。
- Python 3.12 worker。
- Docker Compose 部署。
- PostgreSQL + TimescaleDB + pgvector。
- Redis 预留队列、确认码 TTL 和限流能力。

## 运行命令

```bash
docker compose -f deploy/tokyo/docker-compose.yml --env-file .env up -d --build
mvn -pl services/control-api -am test
python3 -m compileall workers/app
```

## 代码规则

- Controller 保持轻薄，返回统一 `ApiResponse`。
- 业务逻辑放 Service。
- 风控不得放在 Agent prompt 中，必须是代码硬规则。
- 不做大范围无关格式化。
- 不覆盖用户无关改动。
