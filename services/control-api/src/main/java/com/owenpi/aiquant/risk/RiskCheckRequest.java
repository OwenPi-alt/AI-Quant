package com.owenpi.aiquant.risk;

import jakarta.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

public record RiskCheckRequest(
    @NotBlank String market,
    @NotBlank String symbol,
    @NotBlank String direction,
    BigDecimal entryPrice,
    BigDecimal stopLoss,
    List<BigDecimal> takeProfit,
    BigDecimal riskRewardRatio,
    BigDecimal confidence,
    BigDecimal requestedRiskUsd,
    BigDecimal requestedNotionalUsd,
    BigDecimal accountEquityUsd,
    BigDecimal leverage,
    Boolean live,
    String action,
    Map<String, Object> agentJson,
    String decisionId) {

  public RiskCheckRequest(
      String market,
      String symbol,
      String direction,
      BigDecimal entryPrice,
      BigDecimal stopLoss,
      List<BigDecimal> takeProfit,
      BigDecimal riskRewardRatio,
      BigDecimal confidence,
      BigDecimal requestedRiskUsd,
      BigDecimal requestedNotionalUsd,
      BigDecimal accountEquityUsd,
      BigDecimal leverage,
      Boolean live,
      String action,
      Map<String, Object> agentJson) {
    this(market, symbol, direction, entryPrice, stopLoss, takeProfit, riskRewardRatio, confidence,
        requestedRiskUsd, requestedNotionalUsd, accountEquityUsd, leverage, live, action, agentJson, null);
  }
}
