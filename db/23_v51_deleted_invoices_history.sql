-- =====================================================================
-- Aequm Billing v5.1 — Deleted Invoices History & Audit Archiving
--
-- Stores an immutable historical snapshot of every deleted invoice
-- (both Tax and Proforma) including line items, totals, who deleted it,
-- timestamp, and the mandatory reason for deletion.
-- =====================================================================

USE aequm_billing;

CREATE TABLE IF NOT EXISTS deleted_invoices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  original_invoice_id INT NOT NULL,
  doc_no VARCHAR(40) NOT NULL,
  doc_type ENUM('TAX', 'PRO') NOT NULL DEFAULT 'TAX',
  doc_date DATE NOT NULL,
  fy VARCHAR(9) NOT NULL,
  customer_id INT NULL,
  customer_name VARCHAR(160) NOT NULL,
  customer_code VARCHAR(20) NULL,
  customer_gstin VARCHAR(15) NULL,
  po_no VARCHAR(60) NULL,
  taxable_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
  cgst_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
  sgst_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
  igst_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
  total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
  deleted_by_user_id INT NULL,
  deleted_by_name VARCHAR(120) NOT NULL,
  deletion_reason VARCHAR(255) NOT NULL,
  deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  snapshot_json LONGTEXT NOT NULL,
  INDEX idx_di_tenant_fy (tenant_id, fy),
  INDEX idx_di_doc_no (tenant_id, doc_no),
  CONSTRAINT fk_di_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

