-- =====================================================================
-- Aequm Billing v4.6 — discounts and hand-typed document numbers
--
-- 1. invoices.fy           financial year of the document date ("2026-27"),
--                          filled in for every existing invoice
-- 2. invoices.disc_type / disc_value         overall discount
--    invoice_lines.disc_type / disc_value    line discount
-- 3. Document numbers are unique per organisation, document type (tax
--    invoice / proforma) and financial year, instead of per organisation
--    for all time: uq_i (tenant_id, doc_no) becomes
--    uq_i_fy (tenant_id, doc_type, fy, doc_no).
--
-- Additive and safe to run more than once. Existing rows already satisfy
-- the new key, because the old one was stricter.
-- Take a backup first, as for every migration.
-- =====================================================================

USE aequm_billing;

-- ---------------------------------------------------------- 1. invoices.fy
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN fy VARCHAR(9) NULL AFTER doc_date',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'fy'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Backfill from each organisation's financial-year start (default 1 April).
-- The same rule as backend/app/fy.py: a year starting 1 January is labelled
-- "2026", any other start "2026-27".
SET @has_fy_start = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'tenants'
    AND column_name = 'fy_start_month'
);
SET @m = IF(@has_fy_start > 0, 'COALESCE(t.fy_start_month, 4)', '4');
SET @d = IF(@has_fy_start > 0, 'COALESCE(t.fy_start_day, 1)', '1');
SET @start = CONCAT(
  'STR_TO_DATE(CONCAT(YEAR(i.doc_date), ''-'', ', @m, ', ''-'', ',
  'IF(', @m, ' = 2, LEAST(', @d, ', 28), ', @d, ')), ''%Y-%c-%e'')');
SET @y = CONCAT('(YEAR(i.doc_date) - IF(i.doc_date < ', @start, ', 1, 0))');
SET @sql = CONCAT(
  'UPDATE invoices i JOIN tenants t ON t.id = i.tenant_id SET i.fy = ',
  'IF(', @m, ' = 1 AND ', @d, ' = 1, CAST(', @y, ' AS CHAR), ',
  'CONCAT(', @y, ', ''-'', RIGHT(', @y, ' + 1, 2))) ',
  'WHERE i.fy IS NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE invoices MODIFY fy VARCHAR(9) NOT NULL;

-- ------------------------------------------------------------ 2. discounts
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN disc_type ENUM(''PCT'',''AMT'') NULL',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'disc_type'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN disc_value DECIMAL(14,4) NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND column_name = 'disc_value'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN disc_type ENUM(''PCT'',''AMT'') NULL',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoice_lines' AND column_name = 'disc_type'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD COLUMN disc_value DECIMAL(14,4) NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'invoice_lines' AND column_name = 'disc_value'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD CONSTRAINT i_disc_nonneg CHECK (disc_value >= 0)',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE constraint_schema = DATABASE() AND table_name = 'invoices'
    AND constraint_name = 'i_disc_nonneg'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoice_lines ADD CONSTRAINT il_disc_nonneg CHECK (disc_value >= 0)',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE constraint_schema = DATABASE() AND table_name = 'invoice_lines'
    AND constraint_name = 'il_disc_nonneg'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------- 3. numbers unique per type and year
-- Add the new key first, so tenant_id stays indexed for its foreign key
-- while the old key is dropped.
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD UNIQUE KEY uq_i_fy (tenant_id, doc_type, fy, doc_no)',
    'SELECT 1')
  FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND index_name = 'uq_i_fy'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE invoices DROP INDEX uq_i',
    'SELECT 1')
  FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'invoices' AND index_name = 'uq_i'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
