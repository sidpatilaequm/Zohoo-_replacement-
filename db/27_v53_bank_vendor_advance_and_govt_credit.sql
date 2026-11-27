-- =====================================================================
-- Aequm Billing v5.3 — Bank Vendor Advances without Invoices, Government
-- Credits / Statutory Refunds, and Direct OCR PO & Purchase Invoice Creation
--
-- 1. stmt_txn_links.vendor_id      attach bank transactions directly to a
--                                  vendor as an advance / unbilled payment
-- 2. stmt_txn_links.link_type      adds VEND_ADV
-- 3. payments.vendor_id            payments recorded directly against a
--                                  vendor without requiring an invoice
-- 4. payments.p_side               updated check constraint to allow vendor
--                                  advances / direct payments
-- =====================================================================

USE aequm_billing;

-- ------------------------------------------------- 1. stmt_txn_links.vendor_id
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN vendor_id INT NULL AFTER vinv_id',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'vendor_id'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Foreign key for vendor_id on stmt_txn_links
SET @has_fk = (
  SELECT COUNT(*)
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND constraint_name = 'fk_stl_v'
);
SET @sql = IF(@has_fk = 0,
  'ALTER TABLE stmt_txn_links ADD CONSTRAINT fk_stl_v FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE SET NULL',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------------ 2. link_type
ALTER TABLE stmt_txn_links
  MODIFY link_type ENUM('CUST_INV','VEND_INV','EMPLOYEE','DIRECTOR_LOAN','GOVT','VEND_ADV') NOT NULL;

-- ---------------------------------------------------- 3. payments.vendor_id
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE payments ADD COLUMN vendor_id INT NULL AFTER vinv_id',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'payments' AND column_name = 'vendor_id'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Foreign key for vendor_id on payments
SET @has_p_fk = (
  SELECT COUNT(*)
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'payments' AND constraint_name = 'fk_p_v'
);
SET @sql = IF(@has_p_fk = 0,
  'ALTER TABLE payments ADD CONSTRAINT fk_p_v FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE CASCADE',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- --------------------------------------------------- 4. payments.p_side check
SET @has_chk = (
  SELECT COUNT(*)
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'payments' AND constraint_name = 'p_side'
);
SET @drop_chk = IF(@has_chk > 0, 'ALTER TABLE payments DROP CHECK p_side', 'SELECT 1');
PREPARE stmt FROM @drop_chk; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE payments ADD CONSTRAINT p_side CHECK (
  (pay_type = 'REC' AND invoice_id IS NOT NULL AND vinv_id IS NULL AND vendor_id IS NULL) OR
  (pay_type = 'PAY' AND (vinv_id IS NOT NULL OR vendor_id IS NOT NULL) AND invoice_id IS NULL)
);
