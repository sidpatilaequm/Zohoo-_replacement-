-- =====================================================================
-- Aequm Billing v4.5 — directors' signature images on customer invoices
--
-- Run after 12_v44_proforma_email.sql. Additive and safe to run more than
-- once: creates signatories if missing, adds two tenant flags if missing,
-- and grants the Signatures screen to groups that administer the
-- organisation. It does not DROP, TRUNCATE or DELETE anything.
--
--   signatories            name, designation, signature image (PNG data URI),
--                          on_invoices (at most two print at once)
--   tenants.sig_on_tax     print the signatures on tax invoices
--   tenants.sig_on_pro     print the signatures on proforma invoices
-- =====================================================================
USE aequm_billing;

CREATE TABLE IF NOT EXISTS signatories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  name VARCHAR(120) NOT NULL,
  designation VARCHAR(80) NOT NULL DEFAULT 'Director',
  image MEDIUMTEXT NOT NULL,                 -- cleaned PNG, data URI
  on_invoices BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INT NOT NULL DEFAULT 0,
  uploaded_by VARCHAR(120) NULL,
  uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sig_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  KEY ix_sig_t (tenant_id, sort_order)
) ENGINE=InnoDB;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN sig_on_tax BOOLEAN NOT NULL DEFAULT TRUE',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'sig_on_tax');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN sig_on_pro BOOLEAN NOT NULL DEFAULT TRUE',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'sig_on_pro');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'signatures' FROM group_perms WHERE perm = 'org';
