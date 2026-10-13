-- =====================================================================
-- Aequm Billing v4.4 — proforma number range and register, invoice notes,
-- terms and QR, and e-mailing documents through SMTP
--
-- Run after 11_v43_expense_heads.sql. Additive and safe to run more than
-- once: it only adds columns that are missing, creates email_log if it is
-- missing, fills the new notes/terms where they are still empty, and grants
-- the Proforma Register. It does not DROP, TRUNCATE or DELETE anything.
-- Take a backup first all the same.
--
--   tenants.pro_prefix / pro_seq / pro_fy   proforma number range (default PI/001)
--   tenants.inv_notes / inv_terms           printed as Notes and Terms & Conditions
--   invoices.converted_to / _id / _on       a proforma is kept when converted and
--                                           points at the tax invoice it became
--   email_log                               every document mail sent or attempted
--
-- Proformas already on file keep the numbers they have. New proformas start
-- at PI/001 (or the range set in Company Information).
-- =====================================================================
USE aequm_billing;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN pro_prefix VARCHAR(24) NOT NULL DEFAULT ''PI/''',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'pro_prefix');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN pro_seq INT NOT NULL DEFAULT 1',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'pro_seq');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN pro_fy BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'pro_fy');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN inv_notes TEXT NULL',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'inv_notes');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN inv_terms TEXT NULL',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants' AND column_name = 'inv_terms');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN converted_to VARCHAR(40) NULL AFTER converted_from',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'converted_to');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN converted_to_id INT NULL AFTER converted_to',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'converted_to_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN converted_on DATE NULL AFTER converted_to_id',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'converted_on');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- The standing text, only where nobody has set it yet.
UPDATE tenants SET inv_notes = 'Thanks for your business. Pay immediately.'
  WHERE inv_notes IS NULL;
UPDATE tenants SET inv_terms = 'Pay immediately for license activation'
  WHERE inv_terms IS NULL;

CREATE TABLE IF NOT EXISTS email_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  doc_kind VARCHAR(8) NOT NULL,             -- TAX | PRO | PO | TEST
  doc_id INT NULL,
  doc_no VARCHAR(40) NULL,
  sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_by VARCHAR(120) NULL,
  from_addr VARCHAR(200) NULL,
  to_addrs TEXT NOT NULL,
  cc_addrs TEXT NULL,
  bcc_addrs TEXT NULL,
  subject VARCHAR(250) NOT NULL,
  attachments TEXT NULL,
  status VARCHAR(8) NOT NULL DEFAULT 'SENT', -- SENT | FAILED
  error TEXT NULL,
  CONSTRAINT fk_mail_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  KEY ix_mail_doc (tenant_id, doc_kind, doc_id)
) ENGINE=InnoDB;

-- The Proforma Register goes to every group that has the Invoice Register.
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'proforma' FROM group_perms WHERE perm = 'saved';
