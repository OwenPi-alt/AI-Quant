package com.owenpi.aiquant.decision;

import com.owenpi.aiquant.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/decisions")
public class DecisionController {

  private final DecisionService decisionService;

  public DecisionController(DecisionService decisionService) {
    this.decisionService = decisionService;
  }

  @PostMapping
  public ApiResponse<DecisionCreateResponse> create(@Valid @RequestBody DecisionCreateRequest request) {
    return ApiResponse.ok(decisionService.create(request));
  }

  @GetMapping("/{decisionId}")
  public ApiResponse<Map<String, Object>> findById(@PathVariable UUID decisionId) {
    return ApiResponse.ok(decisionService.findById(decisionId));
  }
}
