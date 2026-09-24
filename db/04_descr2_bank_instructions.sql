-- v2.3: second description on document lines, invoice subject/instructions,
-- structured bank details on the organisation.
ALTER TABLE tenants
  ADD COLUMN bank_name VARCHAR(120) NULL AFTER bank,
  ADD COLUMN bank_ifsc VARCHAR(11) NULL AFTER bank_name,
  ADD COLUMN bank_account VARCHAR(30) NULL AFTER bank_ifsc;
ALTER TABLE invoices
  ADD COLUMN subject VARCHAR(200) NULL AFTER cancel_reason,
  ADD COLUMN instructions TEXT NULL AFTER subject;
ALTER TABLE invoice_lines ADD COLUMN descr2 VARCHAR(200) NULL AFTER price;
ALTER TABLE po_lines ADD COLUMN descr2 VARCHAR(200) NULL AFTER price;
ALTER TABLE vendor_invoice_lines ADD COLUMN descr2 VARCHAR(200) NULL AFTER price;
