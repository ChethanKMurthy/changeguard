def display_names(conn) -> list[str]:
    return [row[0] for row in conn.execute("SELECT fullname FROM users ORDER BY fullname")]
