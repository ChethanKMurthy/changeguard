def balance(entries):
    return sum(e["amount"] for e in entries)
