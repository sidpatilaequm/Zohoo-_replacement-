-- v2.2: invoice cancellation and payment reversals.
-- Applied automatically by docker on a fresh database; run by hand on an existing one.
ALTER TABLE invoices
  ADD COLUMN status ENUM('ACTIVE','CANCELLED') NOT NULL DEFAULT 'ACTIVE' AFTER converted_from,
  ADD COLUMN cancelled_on DATE NULL AFTER status,
  ADD COLUMN cancelled_by VARCHAR(120) NULL AFTER cancelled_on,
  ADD COLUMN cancel_reason VARCHAR(200) NULL AFTER cancelled_by;
ALTER TABLE payments
  ADD COLUMN reverses_id INT NULL AFTER narration;
