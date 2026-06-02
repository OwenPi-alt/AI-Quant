# Wiki & Vector Recall

## 向量库

- **库**：pgvector（PostgreSQL 扩展），由 timescale/timescaledb-ha:pg16-all 镜像自带
- **维度**：1536（与 OpenAI text-embedding-3-small / DeepSeek embedding 对齐）
- **索引**：`ivfflat (embedding vector_cosine_ops)`
- **存放**：
  - `experience_memory`：每次自动复盘后写入的具体交易经验
  - `wiki_entry`：手工策展的通用交易经验，预填 15 条种子（V004 migration）

不引入 Milvus/Qdrant；单机场景下 pgvector 在 < 100k 条 1536 维向量上完全够用。

## Wiki 表结构

```sql
wiki_entry (
  id UUID PRIMARY KEY,
  category TEXT,          -- macro / funding / risk / pattern / liquidity / mistake / venue
  symbol TEXT,            -- nullable = 所有品种通用
  market TEXT,            -- nullable = 所有市场通用
  title TEXT,
  body TEXT,
  tags TEXT[],
  source TEXT,            -- manual / rule_distilled / imported
  confidence NUMERIC(4,3),
  weight NUMERIC(4,3),
  embedding vector(1536),
  active BOOLEAN,
  last_used_at TIMESTAMPTZ,
  use_count INT
)
```

## 召回路径

agent-worker 处理每个 signal 时：

1. 拼一段查询文本：`market=X symbol=Y direction=LONG strategy=trend_following_v1 features=(...)`
2. 用 `EmbeddingProvider.embed()` 把查询文本转成 1536 维向量
3. 对 wiki_entry 缺 embedding 的行做 lazy backfill（首次启动后逐步填）
4. pgvector cosine 召回：
   - 5 条 `experience_memory`（相似 + 同品种优先）
   - 5 条 `wiki_entry`（相似 + 全局/品种/市场 匹配）
5. 召回的 wiki 触发 `use_count += 1`、`last_used_at = now()`（用于评估哪些 wiki 真正有用）
6. wiki + experience 注入 `agent_json.wiki_hints[]` / `agent_json.experience_hints[]`
7. Telegram 通知里显示前 3 条 wiki 标题，让你审批前一眼看到

风控边界**不变**：wiki 只能作为参考；硬规则仍由 Java RiskService 把守，wiki 无法绕过。

## EmbeddingProvider 切换

`.env`：

```
# 默认：SHA-256 派生伪向量，零成本，无外部依赖
EMBEDDING_PROVIDER=deterministic

# 切到真实语义 embedding：
EMBEDDING_PROVIDER=openai_compat
EMBEDDING_BASE_URL=https://api.deepseek.com
EMBEDDING_MODEL=deepseek-embedding
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_DIM=1536
```

兼容任何 OpenAI 兼容的 `/v1/embeddings` 端点（DeepSeek / OpenAI / 通义 / Ollama）。

**切换语义后注意**：原 deterministic embedding 与新 embedding **不在一个语义空间**，已写入 `experience_memory.embedding` 和 `wiki_entry.embedding` 的旧向量召回时会失真。建议：

```sql
-- 切换 provider 后清空旧 embedding，等 agent-worker 自动回填
UPDATE wiki_entry SET embedding = NULL;
UPDATE experience_memory SET embedding = NULL;
```

## 管理 wiki

### 查看现有 wiki

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT id, category, symbol, market, title, use_count, last_used_at FROM wiki_entry WHERE active ORDER BY use_count DESC LIMIT 20;"
```

### 看哪些 wiki 命中最多

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "SELECT category, title, use_count, last_used_at FROM wiki_entry ORDER BY use_count DESC LIMIT 10;"
```

### 新增一条 wiki

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant <<'SQL'
INSERT INTO wiki_entry (category, symbol, market, title, body, tags, source, confidence)
VALUES (
  'pattern', 'BTCUSDT', NULL,
  'Volume divergence at swing high warns of reversal',
  'When price prints a new high but the bar volume is < 70% of the previous swing-high bar, the next 4h often retraces 50-70% of the impulse. Use as a hint to take partial profits, not as a standalone short signal.',
  ARRAY['volume','divergence','swing_high'],
  'manual', 0.65
);
SQL
```

embedding 留 NULL，agent-worker 下次跑会自动 embed 填上。

### 关闭某条 wiki

```bash
docker exec aiq-postgres psql -U ai_quant -d ai_quant -c \
  "UPDATE wiki_entry SET active = false WHERE id = '<wiki_id>';"
```

被关闭的 wiki 不再参与召回。

### 把 verified_rule 提炼成 wiki（v2 工作）

当某条 `verified_rule` 累计样本量大 / 胜率高，可以手工 INSERT 到 wiki：

```sql
INSERT INTO wiki_entry (category, title, body, tags, source, confidence)
SELECT 'pattern', condition, action, ARRAY['from_rule'], 'rule_distilled', confidence
FROM verified_rule WHERE id = '<rule_id>';
```

未来可以加一个 wiki-distiller worker 自动做这件事。

## 失败模式

- **embedding provider 调不通**：OpenAICompatEmbedder 内置 fallback 到 DeterministicEmbedder，永远不会阻塞 agent
- **wiki_entry 表为空**：召回返回空数组，agent_json 的 `wiki_hints: []`，不影响主流程
- **pgvector 索引未建**：召回会退化为顺序扫描；< 10k 条时性能影响可忽略
- **embedding 维度不匹配**：`OpenAICompatEmbedder` 会 pad 或 truncate 到 `EMBEDDING_DIM`，并打 WARN
