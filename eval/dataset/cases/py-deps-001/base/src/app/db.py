from sqlalchemy import create_engine


def engine(url: str):
    return create_engine(url, future=True)
