package com.owenpi.aiquant.risk;

import java.math.BigDecimal;
import java.util.List;

public record RiskCheckResult(
    String status,
    List<String> reasons,
    boolean hardRule,
    BigDecimal maxTradeRiskUsd,
    BigDecimal dailyLossLimitUsd,
    BigDecimal weeklyLossLimitUsd,
    boolean liveTradingEnabled) {

  public boolean passed() {
    return "PASS".equals(status);
  }
}
