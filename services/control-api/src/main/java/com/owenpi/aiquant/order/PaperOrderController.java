package com.owenpi.aiquant.order;

import com.owenpi.aiquant.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders")
public class PaperOrderController {

  private final PaperOrderService paperOrderService;

  public PaperOrderController(PaperOrderService paperOrderService) {
    this.paperOrderService = paperOrderService;
  }

  @PostMapping("/paper")
  public ApiResponse<PaperOrderResponse> place(@Valid @RequestBody PaperOrderRequest request) {
    return ApiResponse.ok(paperOrderService.place(request));
  }
}
