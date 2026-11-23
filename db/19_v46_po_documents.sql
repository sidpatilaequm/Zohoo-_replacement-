-- =====================================================================
-- Aequm Billing v4.6 — supporting documents on purchase orders
--
-- Adds po_id to doc_files table so files can be uploaded to purchase orders,
-- and automatically copied to purchase (vendor) invoices upon conversion.
-- =====================================================================

USE aequm_billing;

ALTER TABLE doc_files
  ADD COLUMN po_id INT NULL AFTER vinv_id,
  ADD CONSTRAINT fk_docf_p
    FOREIGN KEY (po_id)
    REFERENCES purchase_orders(id)
    ON DELETE CASCADE,
  ADD KEY ix_docf_po (tenant_id, po_id);

-- Update CHECK constraint to include po_id
ALTER TABLE doc_files DROP CHECK ck_docf_one;
ALTER TABLE doc_files ADD CONSTRAINT ck_docf_one
  CHECK (
    (invoice_id IS NOT NULL) +
    (vinv_id IS NOT NULL) +
    (po_id IS NOT NULL) +
    (stmt_txn_id IS NOT NULL) = 1
  );
