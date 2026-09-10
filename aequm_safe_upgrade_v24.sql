USE aequm_billing;

-- =========================================================
-- v2.3
-- =========================================================

ALTER TABLE tenants
  ADD COLUMN bank_name VARCHAR(120) NULL,
  ADD COLUMN bank_ifsc VARCHAR(11) NULL,
  ADD COLUMN bank_account VARCHAR(30) NULL;

ALTER TABLE invoices
  ADD COLUMN subject VARCHAR(200) NULL,
  ADD COLUMN instructions TEXT NULL;

ALTER TABLE invoice_lines
  ADD COLUMN descr2 VARCHAR(200) NULL;

ALTER TABLE po_lines
  ADD COLUMN descr2 VARCHAR(200) NULL;

ALTER TABLE vendor_invoice_lines
  ADD COLUMN descr2 VARCHAR(200) NULL;

-- =========================================================
-- v2.4
-- =========================================================

ALTER TABLE tenants
  ADD COLUMN fy_start_month TINYINT NOT NULL DEFAULT 4,
  ADD COLUMN fy_start_day TINYINT NOT NULL DEFAULT 1,
  ADD COLUMN inv_fy TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN po_fy TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN vinv_prefix VARCHAR(24) NOT NULL DEFAULT 'PINV/',
  ADD COLUMN vinv_seq INT NOT NULL DEFAULT 1,
  ADD COLUMN vinv_fy TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN cust_prefix VARCHAR(12) NOT NULL DEFAULT 'C',
  ADD COLUMN cust_seq INT NOT NULL DEFAULT 1,
  ADD COLUMN vend_prefix VARCHAR(12) NOT NULL DEFAULT 'V',
  ADD COLUMN vend_seq INT NOT NULL DEFAULT 1,
  ADD COLUMN mat_prefix VARCHAR(12) NOT NULL DEFAULT 'M',
  ADD COLUMN mat_seq INT NOT NULL DEFAULT 1;

ALTER TABLE customers
  ADD COLUMN logo MEDIUMTEXT NULL;

ALTER TABLE vendors
  ADD COLUMN logo MEDIUMTEXT NULL;

ALTER TABLE vendor_invoices
  ADD COLUMN our_no VARCHAR(40) NULL;

CREATE TABLE doc_sequences (
  tenant_id INT NOT NULL,
  kind VARCHAR(12) NOT NULL,
  fy VARCHAR(9) NOT NULL,
  next_no INT NOT NULL DEFAULT 1,
  PRIMARY KEY (tenant_id, kind, fy),
  CONSTRAINT fk_ds_t
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
) ENGINE=InnoDB;
