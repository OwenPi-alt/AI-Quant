package com.owenpi.aiquant.decision;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record DecisionCreateRequest(
    UUID signalId,
    @NotBlank String market,
    @NotBlank String symbol,
    String mode,
    @NotBlank String promptHash,
    @NotBlank String modelName,
    @NotNull Map<String, Object> agentJson,
    List<String> relatedMemoryIds,
    UUID marketSnapshotId,
    List<UUID> newsEventIds) {}
