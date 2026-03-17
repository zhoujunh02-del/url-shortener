from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "mysql+pymysql://root:password@localhost:3306/urlshortener"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class URL(Base):
    __tablename__ = "urls"
    short_code = Column(String(6), primary_key=True)
    original_url = Column(String(2048), nullable=False)

Base.metadata.create_all(engine)