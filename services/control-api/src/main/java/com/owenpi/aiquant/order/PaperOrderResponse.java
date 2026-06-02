package com.owenpi.aiquant.order;

import java.util.List;
import java.util.UUID;

public record PaperOrderResponse(
    UUID orderId,
    UUID positionId,
    String status,
    List<UUID> reviewTaskIds) {}
