from sqlmodel import SQLModel, create_engine, Session as DBSession

engine = create_engine("sqlite:///focus.db", connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with DBSession(engine) as session:
        yield session