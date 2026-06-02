package com.owenpi.aiquant.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ApiAuthFilter extends OncePerRequestFilter {

  private static final Logger log = LoggerFactory.getLogger(ApiAuthFilter.class);

  private final AuthProperties properties;
  private final ObjectMapper objectMapper;

  public ApiAuthFilter(AuthProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.objectMapper = objectMapper;
  }

  @Override
  protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    if (!properties.isEnabled()) {
      chain.doFilter(request, response);
      return;
    }
    String path = request.getRequestURI();
    if (isAnonymous(path) || "OPTIONS".equalsIgnoreCase(request.getMethod())) {
      chain.doFilter(request, response);
      return;
    }
    String token = extractToken(request);
    if (token == null || !constantTimeEquals(token, properties.getToken())) {
      log.warn("auth rejected path={} reason={}",
          path, token == null ? "missing-token" : "token-mismatch");
      writeUnauthorized(response);
      return;
    }
    chain.doFilter(request, response);
  }

  private boolean isAnonymous(String path) {
    if (path == null) {
      return false;
    }
    for (String allowed : properties.getAllowAnonymousPaths()) {
      if (allowed == null || allowed.isBlank()) {
        continue;
      }
      if (allowed.endsWith("/*")) {
        String prefix = allowed.substring(0, allowed.length() - 2);
        if (path.startsWith(prefix)) {
          return true;
        }
      } else if (path.equals(allowed)) {
        return true;
      }
    }
    return false;
  }

  private String extractToken(HttpServletRequest request) {
    String header = request.getHeader("Authorization");
    if (header != null && header.startsWith("Bearer ")) {
      return header.substring("Bearer ".length()).trim();
    }
    String alt = request.getHeader("X-API-Token");
    if (alt != null && !alt.isBlank()) {
      return alt.trim();
    }
    return null;
  }

  private boolean constantTimeEquals(String a, String b) {
    if (a == null || b == null || b.isBlank() || a.length() != b.length()) {
      return false;
    }
    int diff = 0;
    for (int i = 0; i < a.length(); i++) {
      diff |= a.charAt(i) ^ b.charAt(i);
    }
    return diff == 0;
  }

  private void writeUnauthorized(HttpServletResponse response) throws IOException {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json");
    response.setCharacterEncoding(StandardCharsets.UTF_8.name());
    response.getWriter().write(
        objectMapper.writeValueAsString(ApiResponse.error("unauthorized")));
  }
}
