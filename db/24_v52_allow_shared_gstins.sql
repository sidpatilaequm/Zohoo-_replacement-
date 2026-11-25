-- Migration 24: Allow shared GSTINs across customers and vendors
-- Drop global UNIQUE index on gstin in customer_gstins and vendor_gstins
-- and enforce uniqueness per party (customer_id, gstin) and (vendor_id, gstin).

ALTER TABLE customer_gstins DROP INDEX gstin;
ALTER TABLE customer_gstins ADD UNIQUE KEY uq_cg (customer_id, gstin);

ALTER TABLE vendor_gstins DROP INDEX gstin;
ALTER TABLE vendor_gstins ADD UNIQUE KEY uq_vg (vendor_id, gstin);
