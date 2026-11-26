-- =====================================================================
-- Migration 26: Fix Customer Registration for AnH & Co (07ACCFA0369A1Z0)
-- Target customer: Code ZC-0068 / Name 'AnH & Co.' / PAN 'ACCFA0369A'
-- =====================================================================

USE aequm_billing;

-- 1. Remove 07ACCFA0369A1Z0 from any duplicate or dummy customer created previously
DELETE FROM customer_gstins WHERE gstin = '07ACCFA0369A1Z0';

-- 2. Remove duplicate customer 'A N H & Co' if it has no invoices and is not ZC-0068
DELETE c FROM customers c
LEFT JOIN invoices i ON i.customer_id = c.id
WHERE c.name = 'A N H & Co'
  AND c.code != 'ZC-0068'
  AND i.id IS NULL;

-- 3. Ensure the existing customer ZC-0068 is set to B2B and has the correct PAN
UPDATE customers
SET
  party_type = 'B2B',
  pan = 'ACCFA0369A'
WHERE code = 'ZC-0068' OR name = 'AnH & Co.' OR pan = 'ACCFA0369A';

-- 4. Register GSTIN 07ACCFA0369A1Z0 for customer ZC-0068
INSERT INTO customer_gstins (
  customer_id, gstin, state_code, label, is_default
)
SELECT
  c.id, '07ACCFA0369A1Z0', '07', 'Principal place', 1
FROM customers c
WHERE (c.code = 'ZC-0068' OR c.name = 'AnH & Co.' OR c.pan = 'ACCFA0369A')
  AND NOT EXISTS (
    SELECT 1 FROM customer_gstins WHERE gstin = '07ACCFA0369A1Z0'
  )
ORDER BY (c.code = 'ZC-0068') DESC, c.id ASC
LIMIT 1;

-- 5. Backfill the registered GSTIN onto any existing invoices for this customer
UPDATE invoices i
JOIN customers c ON i.customer_id = c.id
SET i.gstin = '07ACCFA0369A1Z0'
WHERE (c.code = 'ZC-0068' OR c.name = 'AnH & Co.' OR c.pan = 'ACCFA0369A')
  AND (i.gstin IS NULL OR i.gstin = '' OR i.gstin = 'Unregistered');
