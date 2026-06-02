package com.owenpi.aiquant.decision;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import com.owenpi.aiquant.risk.RiskCheckRequest;
import com.owenpi.aiquant.risk.RiskCheckResult;
import com.owenpi.aiquant.risk.RiskService;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DecisionService {

  private static final Logger log = LoggerFactory.getLogger(DecisionService.class);
  private static final Set<String> LONG_SET = Set.of("LONG", "BUY");
  private static final Set<String> SHORT_SET = Set.of("SHORT", "SELL");

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;
  private final RiskService riskService;
  private JsonSchema decisionSchema;

  public DecisionService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper, RiskService riskService) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
    this.riskService = riskService;
  }

  @PostConstruct
  void loadSchema() throws IOException {
    JsonSchemaFactory factory = JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012);
    try (InputStream stream = new ClassPathResource("schemas/decision-schema.json").getInputStream()) {
      this.decisionSchema = factory.getSchema(stream);
    }
  }

  @Transactional
  public DecisionCreateResponse create(DecisionCreateRequest request) {
    List<String> validationErrors = validateAgentJson(request.agentJson());
    boolean jsonValid = validationErrors.isEmpty();

    RiskCheckResult risk = riskService.check(toRiskRequest(request));
    List<String> reasons = new ArrayList<>(risk.reasons());
    if (!jsonValid) {
      reasons.add("AGENT_JSON_INVALID");
      reasons.addAll(validationErrors);
      risk = new RiskCheckResult(
          "REJECTED",
          reasons,
          true,
          risk.maxTradeRiskUsd(),
          risk.dailyLossLimitUsd(),
          risk.weeklyLossLimitUsd(),
          risk.liveTradingEnabled());
    }
    UUID decisionId = insertDecision(request, jsonValid, risk);
    if (!reasons.isEmpty()) {
      riskService.writeRiskEvent("PRE_CHECK", decisionId.toString(), reasons);
    }
    return new DecisionCreateResponse(decisionId, jsonValid, risk);
  }

  public Map<String, Object> findById(UUID decisionId) {
    return jdbcTemplate.queryForMap(
        "SELECT * FROM decision_log WHERE id = ?", decisionId);
  }

  private UUID insertDecision(DecisionCreateRequest request, boolean jsonValid, RiskCheckResult risk) {
    String agentJson = toJson(request.agentJson());
    List<String> memories = request.relatedMemoryIds() == null ? List.of() : request.relatedMemoryIds();
    List<UUID> newsIds = request.newsEventIds() == null ? List.of() : request.newsEventIds();
    String mode = request.mode() == null || request.mode().isBlank() ? "PAPER_ONLY" : request.mode();
    BigDecimal confidence = numberValue(request.agentJson().get("confidence"));

    return jdbcTemplate.query(
        "INSERT INTO decision_log "
            + "(signal_id, market, symbol, mode, prompt_hash, model_name, agent_json, json_valid, "
            + "confidence, risk_status, risk_reasons, related_memory_ids, market_snapshot_id, news_event_ids) "
            + "VALUES (?::uuid, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, ?, ?, ?, ?::uuid, ?) "
            + "RETURNING id",
        ps -> {
          setUuid(ps, 1, request.signalId());
          ps.setString(2, request.market());
          ps.setString(3, request.symbol());
          ps.setString(4, mode);
          ps.setString(5, request.promptHash());
          ps.setString(6, request.modelName());
          ps.setString(7, agentJson);
          ps.setBoolean(8, jsonValid);
          ps.setBigDecimal(9, confidence);
          ps.setString(10, risk.status());
          ps.setArray(11, ps.getConnection().createArrayOf("text", risk.reasons().toArray()));
          ps.setArray(12, ps.getConnection().createArrayOf("text", memories.toArray()));
          setUuid(ps, 13, request.marketSnapshotId());
          ps.setArray(14, ps.getConnection().createArrayOf("uuid", newsIds.toArray()));
        },
        rs -> {
          if (!rs.next()) {
            throw new IllegalStateException("decision insert returned no id");
          }
          return UUID.fromString(rs.getString("id"));
        });
  }

  private RiskCheckRequest toRiskRequest(DecisionCreateRequest request) {
    Map<String, Object> json = request.agentJson();
    Map<String, Object> entry = nestedMap(json.get("entry"));
    Map<String, Object> position = nestedMap(json.get("max_position_size"));
    BigDecimal entryPrice = numberValue(firstNonNull(entry.get("max"), entry.get("price"), entry.get("min")));
    return new RiskCheckRequest(
        request.market(),
        request.symbol(),
        stringValue(json.get("direction")),
        entryPrice,
        numberValue(json.get("stop_loss")),
        null,
        numberValue(json.get("risk_reward_ratio")),
        numberValue(json.get("confidence")),
        numberValue(firstNonNull(position.get("risk_usd"), json.get("requested_risk_usd"))),
        numberValue(firstNonNull(position.get("notional_usd"), json.get("requested_notional_usd"))),
        null,
        numberValue(firstNonNull(json.get("leverage"), BigDecimal.ONE)),
        false,
        "OPEN",
        json);
  }

  List<String> validateAgentJson(Map<String, Object> agentJson) {
    List<String> errors = new ArrayList<>();
    if (agentJson == null) {
      errors.add("AGENT_JSON_NULL");
      return errors;
    }
    JsonNode node;
    try {
      node = objectMapper.valueToTree(agentJson);
    } catch (IllegalArgumentException ex) {
      errors.add("AGENT_JSON_TREE_FAILED");
      return errors;
    }
    Set<ValidationMessage> messages = decisionSchema.validate(node);
    for (ValidationMessage message : messages) {
      errors.add("SCHEMA:" + message.getInstanceLocation() + ":" + message.getMessage());
    }
    if (!errors.isEmpty()) {
      log.warn("agent_json schema invalid errors={}", errors);
      return errors;
    }

    String direction = stringValue(agentJson.get("direction")).toUpperCase(Locale.ROOT);
    boolean isLong = LONG_SET.contains(direction);
    boolean isShort = SHORT_SET.contains(direction);
    if (!isLong && !isShort) {
      return errors;
    }

    Map<String, Object> entry = nestedMap(agentJson.get("entry"));
    BigDecimal entryLow = firstPresent(numberValue(entry.get("min")), numberValue(entry.get("price")));
    BigDecimal entryHigh = firstPresent(numberValue(entry.get("max")), numberValue(entry.get("price")));
    BigDecimal stop = numberValue(agentJson.get("stop_loss"));
    List<BigDecimal> tps = new ArrayList<>();
    Object tpRaw = agentJson.get("take_profit");
    if (tpRaw instanceof List<?> list) {
      for (Object value : list) {
        BigDecimal candidate = numberValue(value);
        if (candidate != null) {
          tps.add(candidate);
        }
      }
    }

    if (entryLow != null && entryHigh != null && entryLow.compareTo(entryHigh) > 0) {
      errors.add("ENTRY_MIN_GT_MAX");
    }

    if (stop != null && entryLow != null && entryHigh != null) {
      if (isLong && stop.compareTo(entryLow) >= 0) {
        errors.add("STOP_LOSS_WRONG_SIDE_FOR_LONG");
      }
      if (isShort && stop.compareTo(entryHigh) <= 0) {
        errors.add("STOP_LOSS_WRONG_SIDE_FOR_SHORT");
      }
    }

    for (BigDecimal tp : tps) {
      if (isLong && entryHigh != null && tp.compareTo(entryHigh) <= 0) {
        errors.add("TP_BELOW_ENTRY_FOR_LONG");
        break;
      }
      if (isShort && entryLow != null && tp.compareTo(entryLow) >= 0) {
        errors.add("TP_ABOVE_ENTRY_FOR_SHORT");
        break;
      }
    }

    return errors;
  }

  private String toJson(Object value) {
    try {
      return objectMapper.writeValueAsString(value);
    } catch (JsonProcessingException ex) {
      throw new IllegalArgumentException("invalid json payload", ex);
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> nestedMap(Object value) {
    if (value instanceof Map<?, ?> map) {
      return (Map<String, Object>) map;
    }
    return Map.of();
  }

  private static Object firstNonNull(Object... values) {
    for (Object value : values) {
      if (value != null) {
        return value;
      }
    }
    return null;
  }

  private static BigDecimal firstPresent(BigDecimal... values) {
    for (BigDecimal value : values) {
      if (value != null) {
        return value;
      }
    }
    return null;
  }

  private static String stringValue(Object value) {
    return value == null ? "" : String.valueOf(value);
  }

  private static BigDecimal numberValue(Object value) {
    if (value == null) {
      return null;
    }
    if (value instanceof BigDecimal decimal) {
      return decimal;
    }
    if (value instanceof Number number) {
      return BigDecimal.valueOf(number.doubleValue());
    }
    try {
      return new BigDecimal(String.valueOf(value));
    } catch (NumberFormatException ex) {
      return null;
    }
  }

  private static void setUuid(PreparedStatement ps, int index, UUID value) throws java.sql.SQLException {
    if (value == null) {
      ps.setNull(index, Types.OTHER);
    } else {
      ps.setObject(index, value);
    }
  }
}
