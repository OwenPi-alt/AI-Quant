package com.owenpi.aiquant.approval;

import java.time.Instant;
import java.util.UUID;

public record ApprovalCreateResponse(
    UUID approvalId,
    UUID decisionId,
    String approvalCode,
    Instant expiresAt,
    String command) {}
