from sqlalchemy import Column, Integer, String, Boolean, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
# from pgvector.sqlalchemy import Vector
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    
    attempts = relationship("AttemptLedger", back_populates="user")


class Question(Base):
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, index=True, nullable=False)
    topic = Column(String, index=True, nullable=False)
    sub_topic = Column(String, index=True, nullable=False)
    difficulty_level = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)
    correct_option = Column(String, nullable=False)
    
    # Feedback Fields
    concept_used = Column(Text, nullable=True)
    step_by_step_solution = Column(Text, nullable=True)
    common_trap = Column(Text, nullable=True)
    is_ai_generated = Column(Boolean, default=False)
    
    # Vector Field (commented out for SQLite local demo)
    # embedding = Column(Vector(768), nullable=True) 
    
    attempts = relationship("AttemptLedger", back_populates="question")


class AttemptLedger(Base):
    __tablename__ = 'attempt_ledger'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_taken_seconds = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="attempts")
    question = relationship("Question", back_populates="attempts")
