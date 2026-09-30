-- =====================================================================
-- Aequm Billing v4.5 — Microsoft Entra identity linking
--
-- Adds Microsoft Entra identity information to existing users.
-- Existing password authentication remains unchanged.
-- =====================================================================

USE aequm_billing;

ALTER TABLE users
  ADD COLUMN entra_tenant_id VARCHAR(64) NULL,
  ADD COLUMN entra_object_id VARCHAR(64) NULL,
  ADD UNIQUE KEY uq_users_entra_identity (entra_tenant_id, entra_object_id);