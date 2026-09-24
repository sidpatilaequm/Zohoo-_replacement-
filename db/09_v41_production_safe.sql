-- =====================================================================
-- Aequm Billing v4.1 — PRODUCTION-SAFE UPGRADE
--
-- IMPORTANT:
--   1) Take a full database backup before running this file.
--   2) Run this file against a COPY/staging database first.
--   3) This migration is additive: it does NOT DROP, TRUNCATE or DELETE
--      any business data.
--   4) Do NOT run db/01_schema.sql against an existing production DB.
--
-- File 21 is the baseline. This migration only adds v4/v4.1 structures
-- that may be missing from an older production schema.
-- =====================================================================
USE aequm_billing;

-- Existing v2.3/v2.4 columns, added only when absent.
-- Safe column additions for tenants
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN bank_name VARCHAR(120) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'tenants'
    AND column_name = 'bank_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN bank_ifsc VARCHAR(11) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'tenants'
    AND column_name = 'bank_ifsc'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN bank_account VARCHAR(30) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'tenants'
    AND column_name = 'bank_account'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tenants ADD COLUMN user_limit INT NOT NULL DEFAULT 2',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'tenants'
    AND column_name = 'user_limit'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for invoices
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN subject VARCHAR(200) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'subject'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN instructions TEXT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'instructions'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN bill_addr_id INT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'bill_addr_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN ship_addr_id INT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'ship_addr_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN pos_manual BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'pos_manual'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN price_mode ENUM(''MATERIAL'',''INCL'',''EXCL'') NOT NULL DEFAULT ''MATERIAL''',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'price_mode'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for invoice_lines
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN descr2 VARCHAR(200) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'descr2'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN sgst_pct DECIMAL(5,2) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'sgst_pct'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN cgst_pct DECIMAL(5,2) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'cgst_pct'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN igst_pct DECIMAL(5,2) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'igst_pct'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN rate_label VARCHAR(120) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'rate_label'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN price_inclusive BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoice_lines'
    AND column_name = 'price_inclusive'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for po_lines
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE po_lines ADD COLUMN descr2 VARCHAR(200) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'po_lines'
    AND column_name = 'descr2'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for vendor_invoice_lines
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE vendor_invoice_lines ADD COLUMN descr2 VARCHAR(200) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'vendor_invoice_lines'
    AND column_name = 'descr2'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for customers
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE customers ADD COLUMN logo MEDIUMTEXT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customers'
    AND column_name = 'logo'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE customers ADD COLUMN payment_term_days INT NOT NULL DEFAULT 0',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customers'
    AND column_name = 'payment_term_days'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE customers ADD COLUMN payment_terms VARCHAR(120) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customers'
    AND column_name = 'payment_terms'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for vendors
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE vendors ADD COLUMN logo MEDIUMTEXT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'vendors'
    AND column_name = 'logo'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE vendors ADD COLUMN payment_term_days INT NOT NULL DEFAULT 0',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'vendors'
    AND column_name = 'payment_term_days'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE vendors ADD COLUMN payment_terms VARCHAR(120) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'vendors'
    AND column_name = 'payment_terms'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for vendor_invoices
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE vendor_invoices ADD COLUMN our_no VARCHAR(40) NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'vendor_invoices'
    AND column_name = 'our_no'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for materials
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE materials ADD COLUMN price_inclusive BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'materials'
    AND column_name = 'price_inclusive'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Safe column additions for purchase_orders
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE purchase_orders ADD COLUMN ship_addr_id INT NULL',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'purchase_orders'
    AND column_name = 'ship_addr_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Financial-year document sequence table. Existing rows are preserved.
CREATE TABLE IF NOT EXISTS doc_sequences (
  tenant_id INT NOT NULL,
  kind VARCHAR(12) NOT NULL,
  fy VARCHAR(9) NOT NULL,
  next_no INT NOT NULL DEFAULT 1,
  PRIMARY KEY (tenant_id, kind, fy),
  CONSTRAINT fk_ds_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Multiple addresses per customer/vendor.
CREATE TABLE IF NOT EXISTS party_addresses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  party_kind ENUM('CUSTOMER','VENDOR') NOT NULL,
  party_id INT NOT NULL,
  label VARCHAR(80) NOT NULL,
  addr_type ENUM('BILLING','SHIPPING','BOTH') NOT NULL DEFAULT 'BOTH',
  gstin CHAR(15) NULL,
  addr VARCHAR(255) NOT NULL,
  city VARCHAR(80) NOT NULL,
  state_code CHAR(2) NOT NULL,
  pin CHAR(6) NULL,
  contact VARCHAR(120) NULL,
  phone VARCHAR(20) NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_pa_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_pa_s FOREIGN KEY (state_code) REFERENCES states(code),
  CONSTRAINT pa_gstin CHECK (gstin IS NULL OR
    (CHAR_LENGTH(gstin) = 15 AND LEFT(gstin,2) = state_code)),
  UNIQUE KEY uq_pa (tenant_id, party_kind, party_id, label)
) ENGINE=InnoDB;

-- Multiple permitted HSN/SAC rates.
CREATE TABLE IF NOT EXISTS hsn_rates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hsn_id INT NOT NULL,
  label VARCHAR(120) NOT NULL,
  sgst_pct DECIMAL(5,2) NOT NULL,
  cgst_pct DECIMAL(5,2) NOT NULL,
  igst_pct DECIMAL(5,2) NOT NULL,
  cess_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
  condition_note VARCHAR(255) NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_hr FOREIGN KEY (hsn_id) REFERENCES hsn_codes(id) ON DELETE CASCADE,
  CONSTRAINT hr_split CHECK (ABS(sgst_pct + cgst_pct - igst_pct) < 0.005),
  UNIQUE KEY uq_hr (hsn_id, label)
) ENGINE=InnoDB;

-- Licence reporting view. CREATE OR REPLACE changes only the view definition,
-- never business rows.
CREATE OR REPLACE VIEW v_seats_used AS
SELECT tenant_id, COUNT(*) AS seats
FROM user_roles
GROUP BY tenant_id;

-- Bank and director-card statements. These tables are entirely new and therefore
-- cannot overwrite existing business records.
CREATE TABLE IF NOT EXISTS stmt_accounts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  kind ENUM('BANK','CARD') NOT NULL,
  label VARCHAR(120) NOT NULL,
  holder VARCHAR(120) NULL,
  number_hint VARCHAR(30) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sa_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_sa (tenant_id, kind, label)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS stmt_uploads (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  account_id INT NOT NULL,
  period CHAR(7) NOT NULL,
  filename VARCHAR(200) NOT NULL,
  uploaded_by VARCHAR(120) NULL,
  txns_found INT NOT NULL DEFAULT 0,
  txns_new INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_su_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_su_a FOREIGN KEY (account_id) REFERENCES stmt_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS stmt_txns (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  account_id INT NOT NULL,
  upload_id INT NOT NULL,
  txn_date DATE NOT NULL,
  descr VARCHAR(240) NOT NULL,
  debit DECIMAL(14,2) NOT NULL DEFAULT 0,
  credit DECIMAL(14,2) NOT NULL DEFAULT 0,
  fingerprint CHAR(40) NOT NULL,
  allocation ENUM('NA','UNALLOCATED','COMPANY','PERSONAL') NOT NULL DEFAULT 'NA',
  category VARCHAR(60) NULL,
  notes VARCHAR(200) NULL,
  allocated_by VARCHAR(120) NULL,
  allocated_at TIMESTAMP NULL,
  CONSTRAINT fk_st_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_st_a FOREIGN KEY (account_id) REFERENCES stmt_accounts(id) ON DELETE CASCADE,
  CONSTRAINT fk_st_u FOREIGN KEY (upload_id) REFERENCES stmt_uploads(id) ON DELETE CASCADE,
  UNIQUE KEY uq_st (tenant_id, account_id, fingerprint),
  KEY ix_st_date (tenant_id, account_id, txn_date)
) ENGINE=InnoDB;

-- Grant the two new statement screens to groups that already have Setup/org.
-- INSERT IGNORE makes this safe to run repeatedly.
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'bankstmt' FROM group_perms WHERE perm = 'org';
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'cardstmt' FROM group_perms WHERE perm = 'org';

-- NOTE: Foreign keys for bill_addr_id/ship_addr_id are intentionally not
-- dynamically added here. Existing production databases may already have
-- equivalent constraints under different generated names. The application
-- validates referenced addresses; adding constraints can be handled separately
-- after staging verification if the production schema lacks them.
