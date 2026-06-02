package com.owenpi.aiquant.approval;

import com.owenpi.aiquant.risk.RiskProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {

  private static final Logger log = LoggerFactory.getLogger(ApprovalService.class);
  private static final String INVALID_MESSAGE = "approval invalid";

  private final JdbcTemplate jdbcTemplate;
  private final RiskProperties riskProperties;
  private final ApprovalProperties approvalProperties;
  private final StringRedisTemplate redis;
  private final SecureRandom secureRandom = new SecureRandom();

  public ApprovalService(
      JdbcTemplate jdbcTemplate,
      RiskProperties riskProperties,
      ApprovalProperties approvalProperties,
      StringRedisTemplate redis) {
    this.jdbcTemplate = jdbcTemplate;
    this.riskProperties = riskProperties;
    this.approvalProperties = approvalProperties;
    this.redis = redis;
  }

  @Transactional
  public ApprovalCreateResponse create(ApprovalCreateRequest request) {
    Map<String, Object> decision = decision(request.decisionId());
    if (!"PASS".equals(String.valueOf(decision.get("risk_status")))) {
      throw new IllegalArgumentException("decision risk status is not PASS");
    }
    if (!Boolean.TRUE.equals(decision.get("json_valid"))) {
      throw new IllegalArgumentException("decision json invalid");
    }

    String code = String.format("%06d", secureRandom.nextInt(1_000_000));
    Instant expiresAt = Instant.now()
        .plus(riskProperties.getRisk().getApprovalTtlMinutes(), ChronoUnit.MINUTES);

    UUID approvalId;
    try {
      approvalId = jdbcTemplate.query(
          "INSERT INTO approval_request (decision_id, code_hash, channel, recipient, expires_at) "
              + "VALUES (?, ?, ?, ?, ?) RETURNING id",
          ps -> {
            ps.setObject(1, request.decisionId());
            ps.setString(2, hash(request.decisionId(), code));
            ps.setString(3, request.channel());
            ps.setString(4, request.recipient());
            ps.setObject(5, expiresAt);
          },
          rs -> {
            if (!rs.next()) {
              throw new IllegalStateException("approval insert returned no id");
            }
            return UUID.fromString(rs.getString("id"));
          });
    } catch (DuplicateKeyException ex) {
      throw new IllegalArgumentException("approval already pending for decision");
    }

    jdbcTemplate.update(
        "UPDATE decision_log SET approval_id = ? WHERE id = ?", approvalId, request.decisionId());

    return new ApprovalCreateResponse(
        approvalId,
        request.decisionId(),
        code,
        expiresAt,
        "approve " + request.decisionId() + " " + code);
  }

  @Transactional
  public ApprovalConfirmResponse confirm(ApprovalConfirmRequest request) {
    Set<String> allowed = approvalProperties.operators();
    String operator = request.approvedBy() == null
        ? ""
        : request.approvedBy().trim().toLowerCase(Locale.ROOT);
    if (!allowed.isEmpty() && !allowed.contains(operator)) {
      log.warn("approval confirm operator not in allowlist decision={} operator={}",
          request.decisionId(), operator);
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    Boolean reserved = redis.opsForValue().setIfAbsent(
        "approval:confirm:" + request.decisionId(),
        Instant.now().toString(),
        Duration.ofMinutes(15));
    if (Boolean.FALSE.equals(reserved)) {
      log.warn("approval confirm replay blocked decision={}", request.decisionId());
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    Map<String, Object> approval;
    try {
      approval = latestPendingApproval(request.decisionId());
    } catch (IllegalArgumentException ex) {
      log.warn("approval confirm no pending decision={}", request.decisionId());
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    UUID approvalId = UUID.fromString(String.valueOf(approval.get("id")));
    Instant expiresAt = toInstant(approval.get("expires_at"));
    if (Instant.now().isAfter(expiresAt)) {
      jdbcTemplate.update(
          "UPDATE approval_request SET status = 'EXPIRED' WHERE id = ? AND status = 'PENDING'",
          approvalId);
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    String expectedHash = String.valueOf(approval.get("code_hash"));
    if (!constantTimeEquals(expectedHash, hash(request.decisionId(), request.approvalCode()))) {
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    Instant approvedAt = Instant.now();
    int updated = jdbcTemplate.update(
        "UPDATE approval_request SET status = 'APPROVED', approved_at = ?, approved_by = ? "
            + "WHERE id = ? AND status = 'PENDING'",
        approvedAt, operator, approvalId);
    if (updated != 1) {
      throw new IllegalArgumentException(INVALID_MESSAGE);
    }

    log.info("approval approved decision={} approval={} operator={}",
        request.decisionId(), approvalId, operator);
    return new ApprovalConfirmResponse(approvalId, request.decisionId(), "APPROVED", approvedAt);
  }

  private Map<String, Object> decision(UUID decisionId) {
    try {
      return jdbcTemplate.queryForMap("SELECT * FROM decision_log WHERE id = ?", decisionId);
    } catch (EmptyResultDataAccessException ex) {
      throw new IllegalArgumentException("decision not found");
    }
  }

  private Map<String, Object> latestPendingApproval(UUID decisionId) {
    try {
      return jdbcTemplate.queryForMap(
          "SELECT * FROM approval_request WHERE decision_id = ? AND status = 'PENDING' "
              + "ORDER BY created_at DESC LIMIT 1",
          decisionId);
    } catch (EmptyResultDataAccessException ex) {
      throw new IllegalArgumentException("pending approval not found");
    }
  }

  private String hash(UUID decisionId, String code) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] bytes = digest.digest((decisionId + ":" + code).getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(bytes);
    } catch (NoSuchAlgorithmException ex) {
      throw new IllegalStateException("SHA-256 unavailable", ex);
    }
  }

  private boolean constantTimeEquals(String a, String b) {
    if (a == null || b == null || a.length() != b.length()) {
      return false;
    }
    int diff = 0;
    for (int i = 0; i < a.length(); i++) {
      diff |= a.charAt(i) ^ b.charAt(i);
    }
    return diff == 0;
  }

  private Instant toInstant(Object value) {
    if (value instanceof Instant instant) {
      return instant;
    }
    if (value instanceof java.sql.Timestamp timestamp) {
      return timestamp.toInstant();
    }
    if (value instanceof OffsetDateTime offsetDateTime) {
      return offsetDateTime.toInstant();
    }
    return Instant.parse(String.valueOf(value));
  }
}
