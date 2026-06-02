package com.owenpi.aiquant.risk;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aiq")
public class RiskProperties {

  private String tradingMode = "PAPER_ONLY";
  private boolean liveTradingEnabled;
  private Risk risk = new Risk();

  public String getTradingMode() {
    return tradingMode;
  }

  public void setTradingMode(String tradingMode) {
    this.tradingMode = tradingMode;
  }

  public boolean isLiveTradingEnabled() {
    return liveTradingEnabled;
  }

  public void setLiveTradingEnabled(boolean liveTradingEnabled) {
    this.liveTradingEnabled = liveTradingEnabled;
  }

  public Risk getRisk() {
    return risk;
  }

  public void setRisk(Risk risk) {
    this.risk = risk;
  }

  public static class Risk {
    private BigDecimal accountEquityUsd = BigDecimal.valueOf(1000);
    private BigDecimal minAgentConfidence = BigDecimal.valueOf(0.65);
    private BigDecimal minRiskReward = BigDecimal.valueOf(1.5);
    private BigDecimal maxTradeRiskPct = BigDecimal.valueOf(0.005);
    private BigDecimal maxDailyLossPct = BigDecimal.valueOf(0.02);
    private BigDecimal maxWeeklyLossPct = BigDecimal.valueOf(0.05);
    private int maxConsecutiveLosses = 3;
    private BigDecimal maxLeverage = BigDecimal.valueOf(2);
    private BigDecimal maxSymbolPositionPct = BigDecimal.valueOf(0.20);
    private int maxOpenPositions = 3;
    private int approvalTtlMinutes = 10;
    private BigDecimal maxEntryDeviationPct = BigDecimal.valueOf(0.003);
    private BigDecimal maxSlippagePct = BigDecimal.valueOf(0.002);
    private boolean requireStopLoss = true;
    private boolean requireManualApproval = true;
    private boolean pauseOnMajorNews = true;
    private String polymarketMode = "OBSERVE_ONLY";
    private List<String> symbolWhitelist = new ArrayList<>();
    private List<String> marketWhitelist = new ArrayList<>();

    public BigDecimal getAccountEquityUsd() {
      return accountEquityUsd;
    }

    public void setAccountEquityUsd(BigDecimal accountEquityUsd) {
      this.accountEquityUsd = accountEquityUsd;
    }

    public BigDecimal getMinAgentConfidence() {
      return minAgentConfidence;
    }

    public void setMinAgentConfidence(BigDecimal minAgentConfidence) {
      this.minAgentConfidence = minAgentConfidence;
    }

    public BigDecimal getMinRiskReward() {
      return minRiskReward;
    }

    public void setMinRiskReward(BigDecimal minRiskReward) {
      this.minRiskReward = minRiskReward;
    }

    public BigDecimal getMaxTradeRiskPct() {
      return maxTradeRiskPct;
    }

    public void setMaxTradeRiskPct(BigDecimal maxTradeRiskPct) {
      this.maxTradeRiskPct = maxTradeRiskPct;
    }

    public BigDecimal getMaxDailyLossPct() {
      return maxDailyLossPct;
    }

    public void setMaxDailyLossPct(BigDecimal maxDailyLossPct) {
      this.maxDailyLossPct = maxDailyLossPct;
    }

    public BigDecimal getMaxWeeklyLossPct() {
      return maxWeeklyLossPct;
    }

    public void setMaxWeeklyLossPct(BigDecimal maxWeeklyLossPct) {
      this.maxWeeklyLossPct = maxWeeklyLossPct;
    }

    public int getMaxConsecutiveLosses() {
      return maxConsecutiveLosses;
    }

    public void setMaxConsecutiveLosses(int maxConsecutiveLosses) {
      this.maxConsecutiveLosses = maxConsecutiveLosses;
    }

    public BigDecimal getMaxLeverage() {
      return maxLeverage;
    }

    public void setMaxLeverage(BigDecimal maxLeverage) {
      this.maxLeverage = maxLeverage;
    }

    public BigDecimal getMaxSymbolPositionPct() {
      return maxSymbolPositionPct;
    }

    public void setMaxSymbolPositionPct(BigDecimal maxSymbolPositionPct) {
      this.maxSymbolPositionPct = maxSymbolPositionPct;
    }

    public int getMaxOpenPositions() {
      return maxOpenPositions;
    }

    public void setMaxOpenPositions(int maxOpenPositions) {
      this.maxOpenPositions = maxOpenPositions;
    }

    public int getApprovalTtlMinutes() {
      return approvalTtlMinutes;
    }

    public void setApprovalTtlMinutes(int approvalTtlMinutes) {
      this.approvalTtlMinutes = approvalTtlMinutes;
    }

    public BigDecimal getMaxEntryDeviationPct() {
      return maxEntryDeviationPct;
    }

    public void setMaxEntryDeviationPct(BigDecimal maxEntryDeviationPct) {
      this.maxEntryDeviationPct = maxEntryDeviationPct;
    }

    public BigDecimal getMaxSlippagePct() {
      return maxSlippagePct;
    }

    public void setMaxSlippagePct(BigDecimal maxSlippagePct) {
      this.maxSlippagePct = maxSlippagePct;
    }

    public boolean isRequireStopLoss() {
      return requireStopLoss;
    }

    public void setRequireStopLoss(boolean requireStopLoss) {
      this.requireStopLoss = requireStopLoss;
    }

    public boolean isRequireManualApproval() {
      return requireManualApproval;
    }

    public void setRequireManualApproval(boolean requireManualApproval) {
      this.requireManualApproval = requireManualApproval;
    }

    public boolean isPauseOnMajorNews() {
      return pauseOnMajorNews;
    }

    public void setPauseOnMajorNews(boolean pauseOnMajorNews) {
      this.pauseOnMajorNews = pauseOnMajorNews;
    }

    public String getPolymarketMode() {
      return polymarketMode;
    }

    public void setPolymarketMode(String polymarketMode) {
      this.polymarketMode = polymarketMode;
    }

    public List<String> getSymbolWhitelist() {
      return symbolWhitelist;
    }

    public void setSymbolWhitelist(List<String> symbolWhitelist) {
      this.symbolWhitelist = symbolWhitelist;
    }

    public List<String> getMarketWhitelist() {
      return marketWhitelist;
    }

    public void setMarketWhitelist(List<String> marketWhitelist) {
      this.marketWhitelist = marketWhitelist;
    }
  }
}
