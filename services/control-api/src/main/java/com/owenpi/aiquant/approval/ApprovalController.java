package com.owenpi.aiquant.approval;

import com.owenpi.aiquant.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/approvals")
public class ApprovalController {

  private final ApprovalService approvalService;

  public ApprovalController(ApprovalService approvalService) {
    this.approvalService = approvalService;
  }

  @PostMapping("/request")
  public ApiResponse<ApprovalCreateResponse> create(@Valid @RequestBody ApprovalCreateRequest request) {
    return ApiResponse.ok(approvalService.create(request));
  }

  @PostMapping("/confirm")
  public ApiResponse<ApprovalConfirmResponse> confirm(@Valid @RequestBody ApprovalConfirmRequest request) {
    return ApiResponse.ok(approvalService.confirm(request));
  }
}
