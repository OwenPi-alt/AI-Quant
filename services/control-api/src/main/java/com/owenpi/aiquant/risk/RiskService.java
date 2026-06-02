package com.owenpi.aiquant.risk;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class RiskService {

  private static final Logger log = LoggerFactory.getLogger(RiskService.class);
  private static final Set<String> LONG_DIRECTIONS = Set.of("LONG", "BUY");
  private static final Set<String> SHORT_DIRECTIONS = Set.of("SHORT", "SELL");
  private static final Set<String> OBSERVE_DIRECTIONS = Set.of("OBSERVE", "FLAT");

  private final RiskProperties properties;
  private final JdbcTemplate jdbcTemplate;

  public RiskService(RiskProperties properties, JdbcTemplate jdbcTemplate) {
    this.properties = properties;
    this.jdbcTemplate = jdbcTemplate;
  }

  public RiskCheckResult check(RiskCheckRequest request) {
    return check(request, "PRE_CHECK");
  }

  public RiskCheckResult check(RiskCheckRequest request, String eventType) {
    List<String> reasons = new ArrayList<>();
    RiskProperties.Risk risk = properties.getRisk();
    BigDecimal equity = firstPositive(request.accountEquityUsd(), latestEquity(), risk.getAccountEquityUsd());
    BigDecimal maxTradeRiskUsd = equity.multiply(risk.getMaxTradeRiskPct());
    BigDecimal dailyLossLimitUsd = equity.multiply(risk.getMaxDailyLossPct());
    BigDecimal weeklyLossLimitUsd = equity.multiply(risk.getMaxWeeklyLossPct());

    String normalizedSymbol = safeUpper(request.symbol());
    String normalizedMarket = safeUpper(request.market());
    String normalizedDirection = safeUpper(request.direction());

    if (!risk.getSymbolWhitelist().contains(normalizedSymbol)) {
      reasons.add("SYMBOL_NOT_WHITELISTED");
    }
    if (!risk.getMarketWhitelist().contains(normalizedMarket)) {
      reasons.add("MARKET_NOT_WHITELISTED");
    }
    if (!LONG_DIRECTIONS.contains(normalizedDirection)
        && !SHORT_DIRECTIONS.contains(normalizedDirection)
        && !OBSERVE_DIRECTIONS.contains(normalizedDirection)) {
      reasons.add("DIRECTION_INVALID");
    }

    boolean liveRequested = Boolean.TRUE.equals(request.live()) || normalizedMarket.contains("LIVE");
    if (liveRequested && (!properties.isLiveTradingEnabled()
        || !"LIVE_CONFIRM_REQUIRED".equals(properties.getTradingMode()))) {
      reasons.add("LIVE_TRADING_DISABLED");
    }

    if (normalizedMarket.startsWith("POLYMARKET")
        && !"OBSERVE_ONLY".equals(safeUpper(risk.getPolymarketMode()))) {
      reasons.add("POLYMARKET_NOT_OBSERVE_ONLY");
    }

    boolean directional = LONG_DIRECTIONS.contains(normalizedDirection)
        || SHORT_DIRECTIONS.contains(normalizedDirection);

    if (directional) {
      if (risk.isRequireStopLoss()
          && (request.stopLoss() == null || request.stopLoss().compareTo(BigDecimal.ZERO) <= 0)) {
        reasons.add("NO_VALID_STOP_LOSS");
      } else if (request.stopLoss() != null && request.entryPrice() != null
          && request.entryPrice().compareTo(BigDecimal.ZERO) > 0) {
        if (LONG_DIRECTIONS.contains(normalizedDirection)
            && request.stopLoss().compareTo(request.entryPrice()) >= 0) {
          reasons.add("STOP_LOSS_WRONG_SIDE_FOR_LONG");
        } else if (SHORT_DIRECTIONS.contains(normalizedDirection)
            && request.stopLoss().compareTo(request.entryPrice()) <= 0) {
          reasons.add("STOP_LOSS_WRONG_SIDE_FOR_SHORT");
        }
      }

      if (request.confidence() == null
          || request.confidence().compareTo(risk.getMinAgentConfidence()) < 0) {
        reasons.add("CONFIDENCE_BELOW_MIN");
      }
      if (request.riskRewardRatio() == null
          || request.riskRewardRatio().compareTo(risk.getMinRiskReward()) < 0) {
        reasons.add("RR_BELOW_MIN");
      }
      if (request.requestedRiskUsd() != null
          && request.requestedRiskUsd().compareTo(maxTradeRiskUsd) > 0) {
        reasons.add("TRADE_RISK_ABOVE_LIMIT");
      }
      if (request.leverage() != null
          && request.leverage().compareTo(risk.getMaxLeverage()) > 0) {
        reasons.add("LEVERAGE_ABOVE_LIMIT");
      }
      if (request.requestedNotionalUsd() != null
          && request.requestedNotionalUsd()
              .compareTo(equity.multiply(risk.getMaxSymbolPositionPct())) > 0) {
        reasons.add("SYMBOL_POSITION_ABOVE_LIMIT");
      }
      if (openPositionCount() >= risk.getMaxOpenPositions()) {
        reasons.add("MAX_OPEN_POSITIONS_REACHED");
      }
      if (latestDailyLossAbs().compareTo(dailyLossLimitUsd) >= 0) {
        reasons.add("DAILY_LOSS_LIMIT_REACHED");
      }
      if (latestWeeklyLossAbs().compareTo(weeklyLossLimitUsd) >= 0) {
        reasons.add("WEEKLY_LOSS_LIMIT_REACHED");
      }
      if (latestConsecutiveLosses() >= risk.getMaxConsecutiveLosses()) {
        reasons.add("CONSECUTIVE_LOSS_PAUSE");
      }

      BigDecimal deviation = entryDeviationPct(normalizedSymbol, normalizedMarket, request.entryPrice());
      if (deviation != null && deviation.compareTo(risk.getMaxEntryDeviationPct()) > 0) {
        reasons.add("ENTRY_DEVIATION_TOO_LARGE");
      }
    }

    String status = reasons.isEmpty() ? "PASS" : "REJECTED";
    if (!reasons.isEmpty()) {
      writeRiskEvent(eventType, request.decisionId(), reasons);
      log.warn("risk check rejected eventType={} symbol={} market={} reasons={}",
          eventType, normalizedSymbol, normalizedMarket, reasons);
    }
    return new RiskCheckResult(
        status,
        reasons,
        reasons.isEmpty(),
        maxTradeRiskUsd,
        dailyLossLimitUsd,
        weeklyLossLimitUsd,
        properties.isLiveTradingEnabled());
  }

  public void writeRiskEvent(String eventType, String decisionId, List<String> reasons) {
    String type = eventType == null || eventType.isBlank() ? "RISK_CHECK" : eventType;
    jdbcTemplate.update(
        "INSERT INTO risk_event (event_type, severity, decision_id, reasons, payload) "
            + "VALUES (?, ?, ?::uuid, ?, '{}'::jsonb)",
        ps -> {
          ps.setString(1, type);
          ps.setString(2, reasons.isEmpty() ? "INFO" : "HIGH");
          if (decisionId == null) {
            ps.setNull(3, Types.OTHER);
          } else {
            ps.setString(3, decisionId);
          }
          ps.setArray(4, ps.getConnection().createArrayOf("text", reasons.toArray()));
        });
  }

  public void writeRiskEvent(String decisionId, List<String> reasons) {
    writeRiskEvent("RISK_CHECK", decisionId, reasons);
  }

  private BigDecimal entryDeviationPct(String symbol, String market, BigDecimal entry) {
    if (entry == null || entry.compareTo(BigDecimal.ZERO) <= 0) {
      return null;
    }
    BigDecimal mid = jdbcTemplate.query(
        "SELECT price FROM market_snapshot WHERE symbol = ? AND market = ? AND price IS NOT NULL "
            + "ORDER BY created_at DESC LIMIT 1",
        ps -> {
          ps.setString(1, symbol);
          ps.setString(2, market);
        },
        rs -> rs.next() ? rs.getBigDecimal("price") : null);
    if (mid == null || mid.compareTo(BigDecimal.ZERO) <= 0) {
      return null;
    }
    return entry.subtract(mid).abs().divide(mid, 12, RoundingMode.HALF_UP);
  }

  private BigDecimal latestEquity() {
    return jdbcTemplate.query(
        "SELECT equity_usd FROM account_snapshot ORDER BY created_at DESC LIMIT 1",
        rs -> rs.next() ? rs.getBigDecimal("equity_usd") : null);
  }

  private BigDecimal latestDailyLossAbs() {
    BigDecimal pnl = jdbcTemplate.query(
        "SELECT daily_pnl_usd FROM account_snapshot ORDER BY created_at DESC LIMIT 1",
        rs -> rs.next() ? rs.getBigDecimal("daily_pnl_usd") : BigDecimal.ZERO);
    return pnl == null || pnl.compareTo(BigDecimal.ZERO) >= 0 ? BigDecimal.ZERO : pnl.abs();
  }

  private BigDecimal latestWeeklyLossAbs() {
    BigDecimal pnl = jdbcTemplate.query(
        "SELECT weekly_pnl_usd FROM account_snapshot ORDER BY created_at DESC LIMIT 1",
        rs -> rs.next() ? rs.getBigDecimal("weekly_pnl_usd") : BigDecimal.ZERO);
    return pnl == null || pnl.compareTo(BigDecimal.ZERO) >= 0 ? BigDecimal.ZERO : pnl.abs();
  }

  private int latestConsecutiveLosses() {
    Integer losses = jdbcTemplate.query(
        "SELECT consecutive_losses FROM account_snapshot ORDER BY created_at DESC LIMIT 1",
        rs -> rs.next() ? rs.getInt("consecutive_losses") : 0);
    return losses == null ? 0 : losses;
  }

  private int openPositionCount() {
    Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM trade_position WHERE status = 'OPEN'", Integer.class);
    return count == null ? 0 : count;
  }

  private static String safeUpper(String value) {
    return value == null ? "" : value.toUpperCase(Locale.ROOT);
  }

  private static BigDecimal firstPositive(BigDecimal... values) {
    for (BigDecimal value : values) {
      if (value != null && value.compareTo(BigDecimal.ZERO) > 0) {
        return value;
      }
    }
    return BigDecimal.valueOf(1000);
  }
}
