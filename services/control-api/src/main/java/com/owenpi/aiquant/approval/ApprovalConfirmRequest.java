package com.owenpi.aiquant.approval;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ApprovalConfirmRequest(
    @NotNull UUID decisionId,
    @NotBlank String approvalCode,
    String approvedBy) {}
