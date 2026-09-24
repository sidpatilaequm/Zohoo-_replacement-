-- =====================================================================
--  Pricing basis
--
--  A material is priced either before GST or with GST already in it. The
--  invoice line records which basis was used, so a price change later does
--  not silently re-interpret an invoice already issued.
-- =====================================================================
USE aequm_billing;

ALTER TABLE materials
  ADD COLUMN price_inclusive BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE invoice_lines
  ADD COLUMN price_inclusive BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE invoices
  ADD COLUMN price_mode ENUM('MATERIAL','INCL','EXCL') NOT NULL DEFAULT 'MATERIAL';
