-- Remove the pre-2024 status column.
ALTER TABLE orders DROP COLUMN legacy_status;
