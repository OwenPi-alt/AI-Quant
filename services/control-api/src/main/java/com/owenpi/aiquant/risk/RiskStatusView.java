package com.owenpi.aiquant.risk;

import java.math.BigDecimal;

public record RiskStatusView(
    String tradingMode,
    boolean liveTradingEnabled,
    BigDecimal minAgentConfidence,
    BigDecimal minRiskReward,
    BigDecimal maxTradeRiskPct,
    BigDecimal maxDailyLossPct,
    BigDecimal maxWeeklyLossPct,
    int maxConsecutiveLosses,
    BigDecimal maxLeverage,
    BigDecimal maxSymbolPositionPct,
    int maxOpenPositions,
    int approvalTtlMinutes,
    BigDecimal maxEntryDeviationPct,
    String polymarketMode) {

  public static RiskStatusView from(RiskProperties properties) {
    RiskProperties.Risk risk = properties.getRisk();
    return new RiskStatusView(
        properties.getTradingMode(),
        properties.isLiveTradingEnabled(),
        risk.getMinAgentConfidence(),
        risk.getMinRiskReward(),
        risk.getMaxTradeRiskPct(),
        risk.getMaxDailyLossPct(),
        risk.getMaxWeeklyLossPct(),
        risk.getMaxConsecutiveLosses(),
        risk.getMaxLeverage(),
        risk.getMaxSymbolPositionPct(),
        risk.getMaxOpenPositions(),
        risk.getApprovalTtlMinutes(),
        risk.getMaxEntryDeviationPct(),
        risk.getPolymarketMode());
  }
}
