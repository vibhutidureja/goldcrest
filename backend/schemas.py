from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class QuestionGeneratePrompt(BaseModel):
    subject: str
    topic: str
    difficulty_level: int

# Strict validation schema for LLM structured output
class GeneratedQuestionSchema(BaseModel):
    subject: str
    topic: str
    sub_topic: str
    difficulty_level: int
    question_text: str = Field(description="The question text. Any math must be in LaTeX formatting.")
    options: List[str] = Field(description="Exactly 4 options. Math must be in LaTeX.", min_length=4, max_length=4)
    correct_option: str = Field(description="The exact text of the correct option from the options list.")
    concept_used: str = Field(description="The core mathematical/scientific concept used.")
    step_by_step_solution: str = Field(description="Detailed step-by-step mathematical approach. Math must be in LaTeX.")
    common_trap: str = Field(description="A common mistake students make for this question.")

class AttemptCreate(BaseModel):
    question_id: int
    is_correct: bool
    time_taken_seconds: int

class TopicAccuracy(BaseModel):
    topic: str
    total_attempts: int
    accuracy_percentage: float

class AnalyticsResponse(BaseModel):
    user_id: int
    strong_topics: List[TopicAccuracy]
    weak_topics: List[TopicAccuracy]

class TestGenerateRequest(BaseModel):
    user_id: int

class TestSubmitRequest(BaseModel):
    user_id: int
    attempts: List[AttemptCreate]

class DoubtRequest(BaseModel):
    attempt_id: int
    user_query: str

class DoubtResponse(BaseModel):
    explanation: str
