def pending_orders(conn):
    return conn.execute("SELECT id FROM orders WHERE legacy_status = 'pending'").fetchall()
