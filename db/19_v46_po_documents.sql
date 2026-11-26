-- =====================================================================
-- Aequm Billing v4.6 — supporting documents on purchase orders
--
-- Adds po_id to doc_files table so files can be uploaded to purchase orders,
-- and automatically copied to purchase (vendor) invoices upon conversion.
-- Idempotent and safe to run multiple times.
-- =====================================================================

USE aequm_billing;

-- 1. Add po_id column to doc_files if missing
SET @has_po_id = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'doc_files' AND column_name = 'po_id'
);

SET @sql_po_id = IF(@has_po_id = 0,
  'ALTER TABLE doc_files ADD COLUMN po_id INT NULL AFTER vinv_id, ADD CONSTRAINT fk_docf_p FOREIGN KEY (po_id) REFERENCES purchase_orders(id) ON DELETE CASCADE, ADD KEY ix_docf_po (tenant_id, po_id)',
  'SELECT 1'
);
PREPARE stmt_po FROM @sql_po_id; EXECUTE stmt_po; DEALLOCATE PREPARE stmt_po;

-- 2. Update CHECK constraint ck_docf_one to include po_id
SET @has_chk = (
  SELECT COUNT(*) FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'doc_files' AND constraint_name = 'ck_docf_one'
);

SET @sql_drop = IF(@has_chk > 0,
  'ALTER TABLE doc_files DROP CHECK ck_docf_one',
  'SELECT 1'
);
PREPARE stmt_drop FROM @sql_drop; EXECUTE stmt_drop; DEALLOCATE PREPARE stmt_drop;

ALTER TABLE doc_files ADD CONSTRAINT ck_docf_one
  CHECK (
    (invoice_id IS NOT NULL) +
    (vinv_id IS NOT NULL) +
    (po_id IS NOT NULL) +
    (stmt_txn_id IS NOT NULL) = 1
  );
