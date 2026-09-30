-- =====================================================================
-- Aequm Billing v4.5 — Microsoft SSO one-time handoff
--
-- Stores short-lived, single-use codes used to safely transfer an
-- authenticated Microsoft session to the existing Aequm frontend.
-- =====================================================================

USE aequm_billing;

CREATE TABLE IF NOT EXISTS auth_handoffs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code_hash VARCHAR(64) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  tenant_id INT NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_ah_user
    FOREIGN KEY (user_id)
    REFERENCES users(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_ah_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants(id)
    ON DELETE CASCADE,

  KEY ix_ah_expiry (expires_at),
  KEY ix_ah_user (user_id)
) ENGINE=InnoDB;