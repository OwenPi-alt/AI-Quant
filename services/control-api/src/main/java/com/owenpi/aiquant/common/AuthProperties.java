package com.owenpi.aiquant.common;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aiq.auth")
public class AuthProperties {

  private boolean enabled = true;
  private String token = "";
  private List<String> allowAnonymousPaths = new ArrayList<>();

  public boolean isEnabled() {
    return enabled;
  }

  public void setEnabled(boolean enabled) {
    this.enabled = enabled;
  }

  public String getToken() {
    return token;
  }

  public void setToken(String token) {
    // Trim defensively: env-file values often have trailing newlines or
    // accidental spaces from copy/paste, which would otherwise make every
    // /api/* request return 401 silently.
    this.token = token == null ? "" : token.trim();
  }

  public List<String> getAllowAnonymousPaths() {
    return allowAnonymousPaths;
  }

  public void setAllowAnonymousPaths(List<String> allowAnonymousPaths) {
    this.allowAnonymousPaths = allowAnonymousPaths;
  }
}
