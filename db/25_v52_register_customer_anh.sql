-- =====================================================================
-- Migration 25: Register Customer AnH & Co (GSTIN 07ACCFA0369A1Z0)
-- Safe, additive and idempotent migration for production
-- =====================================================================

USE aequm_billing;

-- 1. Ensure customer ZC-0068 or AnH & Co. exists and has party_type B2B and correct PAN
UPDATE customers
SET
  party_type = 'B2B',
  pan = 'ACCFA0369A'
WHERE code = 'ZC-0068' OR name = 'AnH & Co.' OR pan = 'ACCFA0369A';

-- 2. Insert customer GSTIN registration for ZC-0068
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
