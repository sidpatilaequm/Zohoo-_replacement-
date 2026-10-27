-- =====================================================================
-- Aequm Billing v4.4 — Sales Reports
--
-- Records the user who created each invoice, enabling sales-by-employee
-- reporting. Existing invoices remain NULL (creator not recorded).
-- Additive migration; does not modify existing invoice data.
-- =====================================================================

USE aequm_billing;

ALTER TABLE invoices
  ADD COLUMN created_by_user_id INT NULL,
  ADD CONSTRAINT fk_invoices_created_by_user
    FOREIGN KEY (created_by_user_id)
    REFERENCES users(id)
    ON DELETE SET NULL;

CREATE INDEX ix_invoices_created_by_user
  ON invoices (created_by_user_id);
