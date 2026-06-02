package com.owenpi.aiquant.order;

import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.UUID;

public record PaperOrderRequest(
    @NotNull UUID decisionId,
    BigDecimal entryPrice,
    BigDecimal qty,
    BigDecimal notionalUsd,
    String clientOrderId) {}
