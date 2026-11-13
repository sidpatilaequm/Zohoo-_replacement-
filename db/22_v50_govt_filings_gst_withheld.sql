-- =====================================================================
-- Aequm Billing v5.0 — government filings on the bank statement, GST
-- withheld alongside TDS, and vendor invoices paid from the bank showing
-- on Vendor Payments
--
-- 1. payments.gst_tds              GST withheld by the payer (GST TDS,
--                                  CGST Act s.51) on a receipt or payment
-- 2. stmt_txn_links.gst_tds        the same on a bank statement attachment
-- 3. stmt_txn_links.link_type      adds GOVT (a payment to the government)
-- 4. stmt_txn_links.govt_kind      GST | TDS | PF | ESI | OTHER
--    stmt_txn_links.govt_period    the month the payment is for (YYYY-MM)
--    stmt_txn_links.challan_ref    challan / CPIN / CIN reference
--    stmt_txn_links.govt_descr     what an "other" statutory payment was for
-- 5. Backfill: vendor invoices attached to bank debits or card spends
--    before this release get their payment on Vendor Payments — but ONLY
--    where the vendor invoice has no payment of any kind there yet. Where
--    someone had already entered payments by hand, nothing is posted (that
--    would count the money twice); the application still counts those older
--    attachments when working out what is open.
--
-- Run after 21_v49_bank_receipts.sql. Additive and safe to run more than
-- once. Take a backup first, as for every migration.
-- =====================================================================

USE aequm_billing;

-- --------------------------------------------------------- 1. payments.gst_tds
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE payments ADD COLUMN gst_tds DECIMAL(14,2) NOT NULL DEFAULT 0 AFTER tds',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'payments' AND column_name = 'gst_tds'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------------------- 2. stmt_txn_links.gst_tds
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN gst_tds DECIMAL(14,2) NOT NULL DEFAULT 0 AFTER tds',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'gst_tds'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------------ 3. link_type
ALTER TABLE stmt_txn_links
  MODIFY link_type ENUM('CUST_INV','VEND_INV','EMPLOYEE','DIRECTOR_LOAN','GOVT') NOT NULL;

-- ------------------------------------------------------- 4. government fields
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN govt_kind ENUM(''GST'',''TDS'',''PF'',''ESI'',''OTHER'') NULL AFTER gst_tds',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'govt_kind'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN govt_period VARCHAR(7) NULL AFTER govt_kind',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'govt_period'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN challan_ref VARCHAR(40) NULL AFTER govt_period',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'challan_ref'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE stmt_txn_links ADD COLUMN govt_descr VARCHAR(120) NULL AFTER challan_ref',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'stmt_txn_links' AND column_name = 'govt_descr'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------------ 5. backfill
INSERT INTO payments (tenant_id, pay_type, pay_date, vinv_id, amount, tds, gst_tds,
                      mode, bank_ref, bank_acct, narration)
SELECT l.tenant_id, 'PAY', t.txn_date, l.vinv_id, l.amount, l.tds, l.gst_tds,
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
WHERE l.link_type = 'VEND_INV'
  AND l.payment_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM payments p
                  WHERE p.tenant_id = l.tenant_id AND p.vinv_id = l.vinv_id);

UPDATE stmt_txn_links l
JOIN payments p
  ON p.tenant_id = l.tenant_id
 AND p.vinv_id = l.vinv_id
 AND p.narration = CONCAT('Bank statement attachment #', l.id)
SET l.payment_id = p.id
WHERE l.payment_id IS NULL AND l.link_type = 'VEND_INV';

-- What was left alone: older attachments on vendor invoices that already had
-- payments entered by hand. Review these on Vendor Payments.
SELECT v.doc_no AS vendor_invoice_left_as_is, l.amount, l.tds
FROM stmt_txn_links l JOIN vendor_invoices v ON v.id = l.vinv_id
WHERE l.link_type = 'VEND_INV' AND l.payment_id IS NULL;
