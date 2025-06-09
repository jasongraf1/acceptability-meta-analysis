from sqlalchemy import create_engine, Column, String, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pandas as pd

# Load in the codes
codebook_df = pd.read_csv("codebook_for_app.csv")
code_fields = codebook_df["code"].tolist()

# Define SQLite path
DATABASE_URL = "sqlite:///annotations.db"

# Set up SQLAlchemy engine and session
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

# Define your annotation table
class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    article_index = Column(String, index=True)
    authors = Column(String)
    year = Column(String)
    title = Column(String)
    journal = Column(String)
    url = Column(String)
    searchterms = Column(String)

# Dynamically add all codebook fields as String/Text columns
for field in code_fields:
    setattr(Annotation, field, Column(String))

# Create table if it doesn't exist
Base.metadata.create_all(bind=engine)
