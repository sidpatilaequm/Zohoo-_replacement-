-- =====================================================================
--  Licence seats and the auditor
--
--  A company set is licensed for a fixed number of seats. The auditor
--  occupies one of them, which is the point: the limit is on people who
--  can sign in, not on people who can change things.
-- =====================================================================
USE aequm_billing;

ALTER TABLE tenants
  ADD COLUMN user_limit INT NOT NULL DEFAULT 2;

-- A seat is a role in a company set. Counting roles rather than users is
-- deliberate: one person holding a role in two organisations occupies a
-- seat in each, because they can sign in to each.
CREATE OR REPLACE VIEW v_seats_used AS
SELECT tenant_id, COUNT(*) AS seats
FROM user_roles
GROUP BY tenant_id;
