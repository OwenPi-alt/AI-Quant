package com.owenpi.aiquant.common;

import java.time.Instant;

public record ApiResponse<T>(boolean success, T data, String error, Instant timestamp) {

  public static <T> ApiResponse<T> ok(T data) {
    return new ApiResponse<>(true, data, null, Instant.now());
  }

  public static <T> ApiResponse<T> error(String error) {
    return new ApiResponse<>(false, null, error, Instant.now());
  }
}
