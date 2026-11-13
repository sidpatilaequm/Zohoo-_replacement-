-- =====================================================================
-- Aequm Billing v4.9 — attaching a customer invoice on Bank Statements
-- records the receipt on Customer Payments, so the invoice shows as paid
--
-- 1. stmt_txn_links.payment_id   the receipt an attachment posted
-- 2. Backfill: customer invoices attached before this release get their
--    receipts too — but ONLY where the invoice has no receipt of any kind
--    on Customer Payments yet. Where someone had already entered receipts
--    by hand, nothing is posted (that would count the money twice); the
--    application still counts those older attachments when working out
--    what is open, so nothing can be attached twice either.
--
-- Run after 20_v48_bank_links_tds_directors.sql. Safe to run more than once.
-- Take a backup first, as for every migration.
-- =====================================================================

USE aequm_billing;

-- --------------------------------------------------------- 1. payment_id
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN payment_id INT NULL AFTER tds',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND column_name = 'payment_id'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD CONSTRAINT fk_stl_p FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE SET NULL',
    'SELECT 1')
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links'
    AND constraint_name = 'fk_stl_p'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------------ 2. backfill
INSERT INTO payments (tenant_id, pay_type, pay_date, invoice_id, amount, tds,
                      mode, bank_ref, bank_acct, narration)
SELECT l.tenant_id, 'REC', t.txn_date, l.invoice_id, l.amount, l.tds,
       CASE
         WHEN UPPER(t.descr) LIKE '%UPI%'  THEN 'UPI'
         WHEN UPPER(t.descr) LIKE '%IMPS%' THEN 'IMPS'
         WHEN UPPER(t.descr) LIKE '%RTGS%' THEN 'RTGS'
         WHEN UPPER(t.descr) LIKE '%CHQ%' OR UPPER(t.descr) LIKE '%CHEQUE%'
           OR UPPER(t.descr) LIKE '%CLG%' THEN 'Cheque'
         ELSE 'NEFT'
       END,
       NULLIF(LEFT(t.descr, 60), ''), NULLIF(LEFT(a.label, 80), ''),
       CONCAT('Bank statement attachment #', l.id)
FROM stmt_txn_links l
JOIN stmt_txns t     ON t.id = l.txn_id
JOIN stmt_accounts a ON a.id = t.account_id
JOIN invoices i      ON i.id = l.invoice_id
WHERE l.link_type = 'CUST_INV'
  AND l.payment_id IS NULL
  AND i.doc_type = 'TAX' AND i.status = 'ACTIVE'
  AND NOT EXISTS (SELECT 1 FROM payments p
                  WHERE p.tenant_id = l.tenant_id AND p.invoice_id = l.invoice_id);

UPDATE stmt_txn_links l
JOIN payments p
  ON p.tenant_id = l.tenant_id
 AND p.invoice_id = l.invoice_id
 AND p.narration = CONCAT('Bank statement attachment #', l.id)
SET l.payment_id = p.id
WHERE l.payment_id IS NULL;

-- What was left alone: older attachments on invoices that already had
-- receipts entered by hand. Review these on Customer Payments.
SELECT i.doc_no AS invoice_left_as_is, l.amount, l.tds
FROM stmt_txn_links l JOIN invoices i ON i.id = l.invoice_id
WHERE l.link_type = 'CUST_INV' AND l.payment_id IS NULL;
