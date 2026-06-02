package com.owenpi.aiquant.dashboard;

import com.owenpi.aiquant.common.ApiResponse;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/dashboard")
public class DashboardController {

  private final JdbcTemplate jdbcTemplate;

  public DashboardController(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  @GetMapping("/summary")
  public ApiResponse<Map<String, Object>> summary() {
    Map<String, Object> data = new LinkedHashMap<>();
    data.put("account", jdbcTemplate.query(
        "SELECT * FROM account_snapshot ORDER BY created_at DESC LIMIT 1",
        rs -> rs.next() ? Map.of(
            "equityUsd", rs.getBigDecimal("equity_usd"),
            "availableUsd", rs.getBigDecimal("available_usd"),
            "dailyPnlUsd", rs.getBigDecimal("daily_pnl_usd"),
            "weeklyPnlUsd", rs.getBigDecimal("weekly_pnl_usd"),
            "consecutiveLosses", rs.getInt("consecutive_losses")) : Map.of()));
    data.put("openPositions", count("SELECT COUNT(*) FROM trade_position WHERE status = 'OPEN'"));
    data.put("pendingApprovals", count("SELECT COUNT(*) FROM approval_request WHERE status = 'PENDING'"));
    data.put("recentDecisions", count("SELECT COUNT(*) FROM decision_log WHERE created_at > now() - interval '24 hours'"));
    data.put("riskEvents24h", count("SELECT COUNT(*) FROM risk_event WHERE created_at > now() - interval '24 hours'"));
    return ApiResponse.ok(data);
  }

  private int count(String sql) {
    Integer value = jdbcTemplate.queryForObject(sql, Integer.class);
    return value == null ? 0 : value;
  }
}
