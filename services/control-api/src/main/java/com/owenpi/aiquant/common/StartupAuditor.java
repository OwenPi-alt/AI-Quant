package com.owenpi.aiquant.common;

import com.owenpi.aiquant.approval.ApprovalProperties;
import com.owenpi.aiquant.risk.RiskProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupAuditor {

  private static final Logger log = LoggerFactory.getLogger(StartupAuditor.class);

  private final RiskProperties riskProperties;
  private final AuthProperties authProperties;
  private final ApprovalProperties approvalProperties;

  public StartupAuditor(
      RiskProperties riskProperties,
      AuthProperties authProperties,
      ApprovalProperties approvalProperties) {
    this.riskProperties = riskProperties;
    this.authProperties = authProperties;
    this.approvalProperties = approvalProperties;
  }

  @EventListener(ApplicationReadyEvent.class)
  public void audit() {
    RiskProperties.Risk risk = riskProperties.getRisk();
    String tokenStatus = authProperties.isEnabled()
        ? (authProperties.getToken() == null || authProperties.getToken().isBlank()
            ? "ENABLED_BUT_TOKEN_EMPTY (all /api/* will return 401)"
            : "ENABLED token_len=" + authProperties.getToken().length())
        : "DISABLED (DANGEROUS — set API_AUTH_ENABLED=true)";

    log.info("============================================================");
    log.info("AI-Quant control-api READY");
    log.info("  trading_mode          : {}", riskProperties.getTradingMode());
    log.info("  live_trading_enabled  : {}", riskProperties.isLiveTradingEnabled());
    log.info("  api_auth              : {}", tokenStatus);
    log.info("  approval_operators    : {} (count={})",
        approvalProperties.operators(), approvalProperties.operators().size());
    log.info("  approval_ttl_minutes  : {}", risk.getApprovalTtlMinutes());
    log.info("  approval_active_age   : {} min", approvalProperties.getMaxActiveAgeMinutes());
    log.info("  polymarket_mode       : {}", risk.getPolymarketMode());
    log.info("  min_agent_confidence  : {}", risk.getMinAgentConfidence());
    log.info("  min_risk_reward       : {}", risk.getMinRiskReward());
    log.info("  max_trade_risk_pct    : {}", risk.getMaxTradeRiskPct());
    log.info("  max_daily_loss_pct    : {}", risk.getMaxDailyLossPct());
    log.info("  max_weekly_loss_pct   : {}", risk.getMaxWeeklyLossPct());
    log.info("  max_consec_losses     : {}", risk.getMaxConsecutiveLosses());
    log.info("  max_leverage          : {}", risk.getMaxLeverage());
    log.info("  max_symbol_pos_pct    : {}", risk.getMaxSymbolPositionPct());
    log.info("  max_open_positions    : {}", risk.getMaxOpenPositions());
    log.info("  max_entry_dev_pct     : {}", risk.getMaxEntryDeviationPct());
    log.info("  symbol_whitelist size : {}", risk.getSymbolWhitelist().size());
    log.info("  market_whitelist size : {}", risk.getMarketWhitelist().size());
    log.info("============================================================");

    warnIfMisconfigured(tokenStatus);
  }

  private void warnIfMisconfigured(String tokenStatus) {
    if (tokenStatus.contains("EMPTY")) {
      log.error("API_AUTH_TOKEN is empty — all /api/* requests will return 401 "
          + "until you set API_AUTH_TOKEN in .env and restart control-api.");
    }
    if (!authProperties.isEnabled()) {
      log.error("API_AUTH_ENABLED=false — control-api is wide open. Do not run in production.");
    }
    if (approvalProperties.operators().isEmpty()) {
      log.error("APPROVAL_OPERATORS is empty — confirm() will accept any approvedBy. "
          + "Set APPROVAL_OPERATORS in .env.");
    }
    if (riskProperties.getRisk().getSymbolWhitelist().isEmpty()) {
      log.error("symbol whitelist is empty — every symbol will be rejected by RiskService.");
    }
  }
}
