from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import database_url


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(database_url(), pool_pre_ping=True)


def get_db():
    with sessionmaker(bind=engine(), expire_on_commit=False)() as db:
        yield db
