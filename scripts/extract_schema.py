import sqlalchemy
from src.db.models import Base
from sqlalchemy import create_mock_engine

def dump(sql, *multiparams, **params):
    # Print the SQL for the current table
    print(str(sql.compile(dialect=sqlalchemy.dialects.postgresql.dialect())))

# Create a mock engine to just print the SQL
engine = create_mock_engine("postgresql://", dump)

# Generate schema
Base.metadata.create_all(engine)
