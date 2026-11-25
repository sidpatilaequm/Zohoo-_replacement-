-- Migration 24: PO subject, payment terms, and instructions (description header)
ALTER TABLE purchase_orders
  ADD COLUMN subject VARCHAR(200) NULL AFTER ship_addr,
  ADD COLUMN payment_terms VARCHAR(120) NULL AFTER subject,
  ADD COLUMN instructions TEXT NULL AFTER payment_terms;
