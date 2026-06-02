package com.owenpi.aiquant.order;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.owenpi.aiquant.approval.ApprovalProperties;
import com.owenpi.aiquant.risk.RiskCheckRequest;
import com.owenpi.aiquant.risk.RiskCheckResult;
import com.owenpi.aiquant.risk.RiskService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaperOrderService {

  private static final Logger log = LoggerFactory.getLogger(PaperOrderService.class);

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;
  private final RiskService riskService;
  private final ApprovalProperties approvalProperties;

  public PaperOrderService(
      JdbcTemplate jdbcTemplate,
      ObjectMapper objectMapper,
      RiskService riskService,
      ApprovalProperties approvalProperties) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
    this.riskService = riskService;
    this.approvalProperties = approvalProperties;
  }

  @Transactional
  public PaperOrderResponse place(PaperOrderRequest request) {
    jdbcTemplate.queryForObject(
        "SELECT pg_advisory_xact_lock(hashtext(?))", Long.class, request.decisionId().toString());

    UUID approvalId = ensureApproved(request.decisionId());

    UUID existing = jdbcTemplate.query(
        "SELECT id FROM trade_order WHERE decision_id = ? LIMIT 1",
        ps -> ps.setObject(1, request.decisionId()),
        rs -> rs.next() ? UUID.fromString(rs.getString("id")) : null);
    if (existing != null) {
      log.info("paper order already exists decision={} order={}", request.decisionId(), existing);
      UUID positionId = jdbcTemplate.query(
          "SELECT id FROM trade_position WHERE decision_id = ? LIMIT 1",
          ps -> ps.setObject(1, request.decisionId()),
          rs -> rs.next() ? UUID.fromString(rs.getString("id")) : null);
      List<UUID> tasks = jdbcTemplate.query(
          "SELECT id FROM review_task WHERE decision_id = ?",
          ps -> ps.setObject(1, request.decisionId()),
          (rs, rowNum) -> UUID.fromString(rs.getString("id")));
      return new PaperOrderResponse(existing, positionId, "ALREADY_FILLED", tasks);
    }

    Map<String, Object> decision = decision(request.decisionId());
    Map<String, Object> agentJson = parseJson(decision.get("agent_json"));
    String market = String.valueOf(decision.get("market"));
    String symbol = String.valueOf(decision.get("symbol"));

    BigDecimal entryPrice = firstNonNull(
        request.entryPrice(),
        numberValue(nestedMap(agentJson.get("entry")).get("max")),
        numberValue(nestedMap(agentJson.get("entry")).get("price")),
        numberValue(nestedMap(agentJson.get("entry")).get("min")));
    BigDecimal notional = firstNonNull(
        request.notionalUsd(),
        numberValue(nestedMap(agentJson.get("max_position_size")).get("notional_usd")),
        BigDecimal.valueOf(100));
    BigDecimal qty = firstNonNull(
        request.qty(),
        entryPrice == null || entryPrice.compareTo(BigDecimal.ZERO) <= 0
            ? BigDecimal.ZERO
            : notional.divide(entryPrice, 12, RoundingMode.HALF_UP));
    BigDecimal stopLoss = numberValue(agentJson.get("stop_loss"));
    String side = String.valueOf(agentJson.get("direction")).toUpperCase();
    String clientOrderId = request.clientOrderId() == null || request.clientOrderId().isBlank()
        ? "paper-" + request.decisionId()
        : request.clientOrderId();

    RiskCheckResult risk = riskService.check(
        new RiskCheckRequest(
            market,
            symbol,
            side,
            entryPrice,
            stopLoss,
            null,
            numberValue(agentJson.get("risk_reward_ratio")),
            numberValue(agentJson.get("confidence")),
            numberValue(nestedMap(agentJson.get("max_position_size")).get("risk_usd")),
            notional,
            null,
            numberValue(firstNonNull(agentJson.get("leverage"), BigDecimal.ONE)),
            false,
            "OPEN",
            agentJson,
            request.decisionId().toString()),
        "SECOND_CHECK");
    if (!risk.passed()) {
      throw new IllegalArgumentException("second risk check failed: " + risk.reasons());
    }

    UUID orderId;
    try {
      orderId = insertOrder(request.decisionId(), approvalId, market, symbol, side,
          entryPrice, stopLoss, qty, notional, clientOrderId, agentJson);
    } catch (DuplicateKeyException ex) {
      log.warn("paper order duplicate client_order_id decision={}", request.decisionId());
      throw new IllegalArgumentException("order already placed");
    }
    UUID positionId = insertPosition(request.decisionId(), orderId, market, symbol, side,
        entryPrice, stopLoss, qty, notional, agentJson);
    List<UUID> tasks = createReviewTasks(request.decisionId());
    log.info("paper order placed decision={} order={} position={}",
        request.decisionId(), orderId, positionId);
    return new PaperOrderResponse(orderId, positionId, "PAPER_FILLED", tasks);
  }

  private UUID insertOrder(UUID decisionId, UUID approvalId, String market, String symbol, String side,
      BigDecimal entryPrice, BigDecimal stopLoss, BigDecimal qty, BigDecimal notional,
      String clientOrderId, Map<String, Object> agentJson) {
    String takeProfit = toJson(agentJson.getOrDefault("take_profit", List.of()));
    return jdbcTemplate.query(
        "INSERT INTO trade_order "
            + "(decision_id, approval_id, market, symbol, side, order_type, mode, status, "
            + "entry_price, stop_loss, take_profit, qty, notional_usd, client_order_id, payload) "
            + "VALUES (?, ?, ?, ?, ?, 'MARKET', 'PAPER_ONLY', 'PAPER_FILLED', "
            + "?, ?, CAST(? AS jsonb), ?, ?, ?, CAST(? AS jsonb)) RETURNING id",
        ps -> {
          ps.setObject(1, decisionId);
          ps.setObject(2, approvalId);
          ps.setString(3, market);
          ps.setString(4, symbol);
          ps.setString(5, side);
          ps.setBigDecimal(6, entryPrice);
          ps.setBigDecimal(7, stopLoss);
          ps.setString(8, takeProfit);
          ps.setBigDecimal(9, qty);
          ps.setBigDecimal(10, notional);
          ps.setString(11, clientOrderId);
          ps.setString(12, toJson(Map.of("source", "paper-broker")));
        },
        rs -> {
          if (!rs.next()) {
            throw new IllegalStateException("order insert returned no id");
          }
          return UUID.fromString(rs.getString("id"));
        });
  }

  private UUID insertPosition(UUID decisionId, UUID orderId, String market, String symbol, String side,
      BigDecimal entryPrice, BigDecimal stopLoss, BigDecimal qty, BigDecimal notional, Map<String, Object> agentJson) {
    return jdbcTemplate.query(
        "INSERT INTO trade_position "
            + "(decision_id, order_id, market, symbol, direction, status, entry_price, stop_loss, take_profit, qty, notional_usd) "
            + "VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, CAST(? AS jsonb), ?, ?) RETURNING id",
        ps -> {
          ps.setObject(1, decisionId);
          ps.setObject(2, orderId);
          ps.setString(3, market);
          ps.setString(4, symbol);
          ps.setString(5, side);
          ps.setBigDecimal(6, entryPrice);
          ps.setBigDecimal(7, stopLoss);
          ps.setString(8, toJson(agentJson.getOrDefault("take_profit", List.of())));
          ps.setBigDecimal(9, qty);
          ps.setBigDecimal(10, notional);
        },
        rs -> {
          if (!rs.next()) {
            throw new IllegalStateException("position insert returned no id");
          }
          return UUID.fromString(rs.getString("id"));
        });
  }

  private List<UUID> createReviewTasks(UUID decisionId) {
    List<UUID> ids = new ArrayList<>();
    ids.add(insertReviewTask(decisionId, "24h", Instant.now().plus(24, ChronoUnit.HOURS)));
    ids.add(insertReviewTask(decisionId, "48h", Instant.now().plus(48, ChronoUnit.HOURS)));
    ids.add(insertReviewTask(decisionId, "7d", Instant.now().plus(7, ChronoUnit.DAYS)));
    return ids;
  }

  private UUID insertReviewTask(UUID decisionId, String window, Instant dueAt) {
    return jdbcTemplate.query(
        "INSERT INTO review_task (decision_id, window_name, due_at) VALUES (?, ?, ?) RETURNING id",
        ps -> {
          ps.setObject(1, decisionId);
          ps.setString(2, window);
          ps.setObject(3, dueAt);
        },
        rs -> {
          if (!rs.next()) {
            throw new IllegalStateException("review task insert returned no id");
          }
          return UUID.fromString(rs.getString("id"));
        });
  }

  private UUID ensureApproved(UUID decisionId) {
    int maxAgeMinutes = approvalProperties.getMaxActiveAgeMinutes();
    UUID approvalId = jdbcTemplate.query(
        "SELECT id FROM approval_request WHERE decision_id = ? AND status = 'APPROVED' "
            + "AND approved_at > now() - make_interval(mins => ?) ORDER BY approved_at DESC LIMIT 1",
        ps -> {
          ps.setObject(1, decisionId);
          ps.setInt(2, maxAgeMinutes);
        },
        rs -> rs.next() ? UUID.fromString(rs.getString("id")) : null);
    if (approvalId == null) {
      throw new IllegalArgumentException("manual approval required or expired");
    }
    return approvalId;
  }

  private Map<String, Object> decision(UUID decisionId) {
    try {
      return jdbcTemplate.queryForMap("SELECT * FROM decision_log WHERE id = ?", decisionId);
    } catch (EmptyResultDataAccessException ex) {
      throw new IllegalArgumentException("decision not found");
    }
  }

  private Map<String, Object> parseJson(Object value) {
    try {
      return objectMapper.readValue(String.valueOf(value), new TypeReference<>() {});
    } catch (JsonProcessingException ex) {
      throw new IllegalArgumentException("decision agent_json invalid", ex);
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> nestedMap(Object value) {
    if (value instanceof Map<?, ?> map) {
      return (Map<String, Object>) map;
    }
    return Map.of();
  }

  private String toJson(Object value) {
    try {
      return objectMapper.writeValueAsString(value);
    } catch (JsonProcessingException ex) {
      throw new IllegalArgumentException("invalid json payload", ex);
    }
  }

  @SafeVarargs
  private static <T> T firstNonNull(T... values) {
    for (T value : values) {
      if (value != null) {
        return value;
      }
    }
    return null;
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
}
