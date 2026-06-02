package com.owenpi.aiquant;

import com.owenpi.aiquant.approval.ApprovalProperties;
import com.owenpi.aiquant.common.AuthProperties;
import com.owenpi.aiquant.risk.RiskProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({RiskProperties.class, AuthProperties.class, ApprovalProperties.class})
public class AiQuantApplication {

  public static void main(String[] args) {
    SpringApplication.run(AiQuantApplication.class, args);
  }
}
