-- =====================================================================
-- Aequm Billing v4.8 — bank statement: employee credits, director loans,
-- and TDS on invoices settled from the bank statement
--
-- 1. directors                 name, DIN, PAN of directors who lend money
-- 2. stmt_txn_links.link_type  adds DIRECTOR_LOAN
--                                credit → loan received from a director
--                                debit  → loan repaid to a director
-- 3. stmt_txn_links.purpose    adds REFUND (money an employee paid back,
--                              attached to a bank credit)
-- 4. stmt_txn_links.director_id
-- 5. stmt_txn_links.tds        TDS on an invoice attachment: the invoice
--                              amount less the money collected. It shows in
--                              the TDS register and the TDS report.
--
-- Additive and safe to run more than once. The ENUM changes only add
-- values, so existing rows are untouched.
-- Take a backup first, as for every migration.
-- =====================================================================

USE aequm_billing;

-- ------------------------------------------------------------ 1. directors
CREATE TABLE IF NOT EXISTS directors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  name VARCHAR(120) NOT NULL,
  din VARCHAR(8) NULL,
  pan VARCHAR(10) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_dir_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_dir_name (tenant_id, name)
) ENGINE=InnoDB;

-- ------------------------------------------------- 2 & 3. enum values
ALTER TABLE stmt_txn_links
  MODIFY link_type ENUM('CUST_INV','VEND_INV','EMPLOYEE','DIRECTOR_LOAN') NOT NULL;

ALTER TABLE stmt_txn_links
  MODIFY purpose ENUM('SALARY','EXPENSE','REFUND') NULL;

-- ------------------------------------------------------ 4. director_id
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN director_id INT NULL AFTER expense_id',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND column_name = 'director_id'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD CONSTRAINT fk_stl_d FOREIGN KEY (director_id) REFERENCES directors(id)',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND constraint_name = 'fk_stl_d'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD KEY ix_stl_dir (tenant_id, director_id)',
    'SELECT 1')
  FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND index_name = 'ix_stl_dir'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- -------------------------------------------------------------- 5. tds
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN tds DECIMAL(14,2) NOT NULL DEFAULT 0 AFTER amount',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND column_name = 'tds'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
