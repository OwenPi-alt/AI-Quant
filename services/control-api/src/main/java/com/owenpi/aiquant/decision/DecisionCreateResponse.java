package com.owenpi.aiquant.decision;

import com.owenpi.aiquant.risk.RiskCheckResult;
import java.util.UUID;

public record DecisionCreateResponse(UUID decisionId, boolean jsonValid, RiskCheckResult risk) {}
