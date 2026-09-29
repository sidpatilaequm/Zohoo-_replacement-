-- =====================================================================
-- Aequm Billing v4.3 — expense master
--
-- Run after 10_v42_employees_bank_links.sql. Additive and safe to run more
-- than once: creates expense_heads, adds stmt_txn_links.expense_id (with its
-- foreign key) only if missing, and grants the Expenses screen.
-- =====================================================================
USE aequm_billing;

CREATE TABLE IF NOT EXISTS expense_heads (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  exp_code VARCHAR(20) NOT NULL,            -- Expense ID, e.g. EXP001
  name VARCHAR(80) NOT NULL,                -- Expense name, e.g. Travel
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_exph_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_exph_code (tenant_id, exp_code),
  UNIQUE KEY uq_exph_name (tenant_id, name)
) ENGINE=InnoDB;

-- The head an employee expense is booked to.
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN expense_id INT NULL AFTER purpose',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND column_name = 'expense_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD CONSTRAINT fk_stl_x2 FOREIGN KEY (expense_id) REFERENCES expense_heads(id)',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND constraint_name = 'fk_stl_x2');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'expenses' FROM group_perms WHERE perm = 'org';
