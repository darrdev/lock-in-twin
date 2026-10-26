from sqlmodel import SQLModel, create_engine, Session as DBSession

engine = create_engine("sqlite:///focus.db")

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with DBSession(engine) as session:
        yield session