
-- =====================================================================
-- Aequm Billing v4.4 — Sales Reports
--
-- Records the user who created each invoice, enabling sales-by-employee
-- reporting. Existing invoices retain NULL creator attribution.
-- Safe to rerun when the column, foreign key, or index already exists.
-- =====================================================================

USE aequm_billing;

-- Add the creator column only if missing.
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD COLUMN created_by_user_id INT NULL',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND column_name = 'created_by_user_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add the foreign key only if missing.
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE invoices ADD CONSTRAINT fk_invoices_created_by_user FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE constraint_schema = DATABASE()
    AND table_name = 'invoices'
    AND constraint_name = 'fk_invoices_created_by_user'
    AND constraint_type = 'FOREIGN KEY'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add the index only if missing.
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX ix_invoices_created_by_user ON invoices (created_by_user_id)',
    'SELECT 1')
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'invoices'
    AND index_name = 'ix_invoices_created_by_user'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
