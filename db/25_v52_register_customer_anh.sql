-- =====================================================================
-- Migration 25: Register Customer A N H & Co (GSTIN 07ACCFA0369A1Z0)
-- Safe, additive and idempotent migration for production
-- =====================================================================

USE aequm_billing;

-- 1. Insert customer for tenant 1 if GSTIN 07ACCFA0369A1Z0 is not already registered
INSERT INTO customers (
  tenant_id, code, name, party_type,
  bill_addr, bill_city, bill_state, bill_pin,
  ship_same, ship_addr, ship_city, ship_state, ship_pin,
  pan, email, payment_terms, payment_term_days
)
SELECT
  1,
  CONCAT('C', LPAD(COALESCE((SELECT MAX(CAST(SUBSTRING(c2.code, 2) AS UNSIGNED)) + 1 FROM customers c2 WHERE c2.tenant_id = 1 AND c2.code REGEXP '^C[0-9]+$'), 1), 4, '0')),
  'A N H & Co', 'B2B',
  '8th floor, 3083, Beverly hills apartment, Geeta Colony, Block-5, New Delhi', 'New Delhi', '07', '110031',
  1, '8th floor, 3083, Beverly hills apartment, Geeta Colony, Block-5, New Delhi', 'New Delhi', '07', '110031',
  'ACCFA0369A', 'himanshu.agarwal@anh.org.in', 'Due on Receipt', 0
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM customer_gstins WHERE gstin = '07ACCFA0369A1Z0'
);

-- 2. Insert customer GSTIN registration
INSERT INTO customer_gstins (
  customer_id, gstin, state_code, label, is_default
)
SELECT
  c.id, '07ACCFA0369A1Z0', '07', 'Principal place', 1
FROM customers c
WHERE c.name = 'A N H & Co' AND c.tenant_id = 1
  AND NOT EXISTS (
    SELECT 1 FROM customer_gstins WHERE gstin = '07ACCFA0369A1Z0'
  )
ORDER BY c.id DESC LIMIT 1;
