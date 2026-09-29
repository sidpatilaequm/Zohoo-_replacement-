-- =====================================================================
-- Aequm Billing v4.4 — documents on invoices
--
-- Run after the existing v4.2 migrations.
-- Additive and safe to run more than once: it only creates doc_files
-- if it is missing.
--
-- Card spends attached to vendor invoices use the existing
-- stmt_txn_links table, and deleting a statement needs no schema change,
-- so this is the only table v4.4 adds.
-- =====================================================================

USE aequm_billing;

CREATE TABLE IF NOT EXISTS doc_files (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  invoice_id INT NULL,
  vinv_id INT NULL,
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

  CONSTRAINT ck_docf_one
    CHECK ((invoice_id IS NULL) <> (vinv_id IS NULL)),

  KEY ix_docf_inv (tenant_id, invoice_id),
  KEY ix_docf_vinv (tenant_id, vinv_id)
) ENGINE=InnoDB;