-- =====================================================================
-- Aequm Billing v4.4 — supporting documents
--
-- Supports documents on:
--   1. Customer invoices
--   2. Vendor invoices
--   3. Bank/card statement transactions
--
-- Additive and safe for fresh installations.
-- =====================================================================

USE aequm_billing;

CREATE TABLE IF NOT EXISTS doc_files (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,

  invoice_id INT NULL,
  vinv_id INT NULL,
  stmt_txn_id INT NULL,

  filename VARCHAR(200) NOT NULL,
  content_type VARCHAR(100) NOT NULL,
  size_bytes INT NOT NULL,
  content MEDIUMBLOB NOT NULL,
  notes VARCHAR(200) NULL,
  uploaded_by VARCHAR(120) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_docf_t
    FOREIGN KEY (tenant_id)
    REFERENCES tenants(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_docf_i
    FOREIGN KEY (invoice_id)
    REFERENCES invoices(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_docf_v
    FOREIGN KEY (vinv_id)
    REFERENCES vendor_invoices(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_docf_s
    FOREIGN KEY (stmt_txn_id)
    REFERENCES stmt_txns(id)
    ON DELETE CASCADE,

  CONSTRAINT ck_docf_one
    CHECK (
      (invoice_id IS NOT NULL) +
      (vinv_id IS NOT NULL) +
      (stmt_txn_id IS NOT NULL) = 1
    ),

  KEY ix_docf_inv (tenant_id, invoice_id),
  KEY ix_docf_vinv (tenant_id, vinv_id),
  KEY ix_docf_stmt (tenant_id, stmt_txn_id)
) ENGINE=InnoDB;