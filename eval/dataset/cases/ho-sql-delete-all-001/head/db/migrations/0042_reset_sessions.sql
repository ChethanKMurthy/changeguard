-- Clear stale sessions after the auth migration.
DELETE FROM sessions;
