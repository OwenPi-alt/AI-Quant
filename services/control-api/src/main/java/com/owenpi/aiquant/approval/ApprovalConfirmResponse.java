package com.owenpi.aiquant.approval;

import java.time.Instant;
import java.util.UUID;

public record ApprovalConfirmResponse(UUID approvalId, UUID decisionId, String status, Instant approvedAt) {}
