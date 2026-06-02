package com.owenpi.aiquant.risk;

import com.owenpi.aiquant.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/risk")
public class RiskController {

  private final RiskService riskService;
  private final RiskProperties properties;

  public RiskController(RiskService riskService, RiskProperties properties) {
    this.riskService = riskService;
    this.properties = properties;
  }

  @PostMapping("/check")
  public ApiResponse<RiskCheckResult> check(@Valid @RequestBody RiskCheckRequest request) {
    return ApiResponse.ok(riskService.check(request));
  }

  @GetMapping("/status")
  public ApiResponse<RiskStatusView> status() {
    return ApiResponse.ok(RiskStatusView.from(properties));
  }
}
