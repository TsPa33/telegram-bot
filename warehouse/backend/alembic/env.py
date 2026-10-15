from alembic import context
from sqlalchemy import create_engine
from app.config import database_url
from app.db import Base
import app.models  # noqa: F401

config = context.config
if context.is_offline_mode():
    context.configure(
        url=database_url(), target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:

    def run(connection):
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()

    external = config.attributes.get("connection")
    if external is not None:
        run(external)
    else:
        with create_engine(database_url()).connect() as connection:
            run(connection)
