package com.owenpi.aiquant.decision;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.owenpi.aiquant.risk.RiskService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.jdbc.core.JdbcTemplate;

class DecisionServiceValidationTest {

  private DecisionService service;

  @BeforeEach
  void setUp() throws Exception {
    service = new DecisionService(
        Mockito.mock(JdbcTemplate.class),
        new ObjectMapper(),
        Mockito.mock(RiskService.class));
    service.loadSchema();
  }

  @Test
  void rejectsNull() {
    assertThat(service.validateAgentJson(null)).contains("AGENT_JSON_NULL");
  }

  @Test
  void rejectsMissingRequiredFields() {
    Map<String, Object> json = Map.of("symbol", "BTCUSDT");
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).isNotEmpty();
  }

  @Test
  void rejectsStopLossWrongSideForLong() {
    Map<String, Object> json = baseAgentJson("LONG");
    json.put("stop_loss", 70000.0);
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).contains("STOP_LOSS_WRONG_SIDE_FOR_LONG");
  }

  @Test
  void rejectsStopLossWrongSideForShort() {
    Map<String, Object> json = baseAgentJson("SHORT");
    json.put("stop_loss", 60000.0);
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).contains("STOP_LOSS_WRONG_SIDE_FOR_SHORT");
  }

  @Test
  void rejectsTakeProfitWrongSideForLong() {
    Map<String, Object> json = baseAgentJson("LONG");
    json.put("take_profit", List.of(65000.0));
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).contains("TP_BELOW_ENTRY_FOR_LONG");
  }

  @Test
  void acceptsValidLong() {
    Map<String, Object> json = baseAgentJson("LONG");
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).isEmpty();
  }

  @Test
  void rejectsConfidenceOutOfRange() {
    Map<String, Object> json = baseAgentJson("LONG");
    json.put("confidence", 1.5);
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).isNotEmpty();
  }

  @Test
  void rejectsEntryMinGreaterThanMax() {
    Map<String, Object> json = baseAgentJson("LONG");
    json.put("entry", Map.of("type", "LIMIT", "min", 68000.0, "max", 67000.0));
    List<String> errors = service.validateAgentJson(json);
    assertThat(errors).contains("ENTRY_MIN_GT_MAX");
  }

  private static HashMap<String, Object> baseAgentJson(String direction) {
    HashMap<String, Object> json = new HashMap<>();
    json.put("symbol", "BTCUSDT");
    json.put("market", "BINANCE_FUTURES_PAPER");
    json.put("direction", direction);
    json.put("entry", Map.of("type", "LIMIT", "min", 67000.0, "max", 67500.0));
    json.put("stop_loss", "LONG".equals(direction) ? 66500.0 : 68500.0);
    json.put("take_profit",
        "LONG".equals(direction) ? List.of(68500.0, 69000.0) : List.of(66000.0, 65500.0));
    json.put("risk_reward_ratio", 2.0);
    json.put("confidence", 0.72);
    json.put("max_position_size", Map.of("notional_usd", 100.0, "risk_usd", 5.0));
    json.put("invalidation_condition", "price closes beyond stop");
    json.put("reasoning_summary", "test");
    json.put("related_memories", List.of());
    json.put("news_sources", List.of());
    json.put("sentiment_score", 0.0);
    json.put("risk_flags", List.of("PAPER_ONLY"));
    return json;
  }
}
