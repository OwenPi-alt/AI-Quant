package com.owenpi.aiquant.approval;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aiq.approval")
public class ApprovalProperties {

  private String operatorAllowlist = "operator";
  private int maxActiveAgeMinutes = 10;

  public String getOperatorAllowlist() {
    return operatorAllowlist;
  }

  public void setOperatorAllowlist(String operatorAllowlist) {
    this.operatorAllowlist = operatorAllowlist;
  }

  public int getMaxActiveAgeMinutes() {
    return maxActiveAgeMinutes;
  }

  public void setMaxActiveAgeMinutes(int maxActiveAgeMinutes) {
    this.maxActiveAgeMinutes = maxActiveAgeMinutes;
  }

  public Set<String> operators() {
    if (operatorAllowlist == null || operatorAllowlist.isBlank()) {
      return Collections.emptySet();
    }
    Set<String> set = new HashSet<>();
    for (String token : Arrays.asList(operatorAllowlist.split(","))) {
      String normalized = token.trim().toLowerCase(Locale.ROOT);
      if (!normalized.isEmpty()) {
        set.add(normalized);
      }
    }
    return set;
  }
}
