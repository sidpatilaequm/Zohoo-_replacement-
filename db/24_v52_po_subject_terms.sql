-- =====================================================================
-- Migration 24: v5.2 PO subject, payment terms, and instructions
-- Safe, additive and idempotent migration for production
-- =====================================================================

USE aequm_billing;

-- 1. purchase_orders.subject
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE purchase_orders ADD COLUMN subject VARCHAR(200) NULL AFTER ship_addr',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'purchase_orders' AND column_name = 'subject'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2. purchase_orders.payment_terms
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE purchase_orders ADD COLUMN payment_terms VARCHAR(120) NULL AFTER subject',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'purchase_orders' AND column_name = 'payment_terms'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3. purchase_orders.instructions
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE purchase_orders ADD COLUMN instructions TEXT NULL AFTER payment_terms',
    'SELECT 1')
  FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'purchase_orders' AND column_name = 'instructions'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
