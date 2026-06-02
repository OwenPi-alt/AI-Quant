package com.owenpi.aiquant.approval;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ApprovalCreateRequest(
    @NotNull UUID decisionId,
    @NotBlank String channel,
    @NotBlank String recipient) {}
