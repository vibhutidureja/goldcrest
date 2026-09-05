import os
import json
from ollama import Client
from fastmcp import FastMCP
from pydantic import ValidationError
from database import SessionLocal
from models import Question, AttemptLedger
from schemas import GeneratedQuestionSchema

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
client = Client(host=OLLAMA_HOST)
MODEL_NAME = "llama3" # Default local model for generation

# Initialize FastMCP Server for the RAG Tools
mcp = FastMCP("JEE_RAG_Server")

@mcp.tool()
def retrieve_question_context(question_id: int) -> str:
    """Retrieve the question context, options, correct answer, and step-by-step solution from the database."""
    db = SessionLocal()
    try:
        q = db.query(Question).filter(Question.id == question_id).first()
        if not q:
            return "Question not found."
        context = (
            f"Question: {q.question_text}\n"
            f"Options: {json.dumps(q.options)}\n"
            f"Correct Answer: {q.correct_option}\n"
            f"Concept: {q.concept_used}\n"
            f"Solution: {q.step_by_step_solution}\n"
            f"Common Trap: {q.common_trap}"
        )
        return context
    finally:
        db.close()

def generate_questions_for_topic(subject: str, topic: str, difficulty: int, num_questions: int = 1):
    """Background task to generate questions using Ollama and strict Pydantic validation."""
    db = SessionLocal()
    try:
        for _ in range(num_questions):
            prompt = f"Generate a JEE level multiple choice question for Subject: {subject}, Topic: {topic}, Difficulty (1-5): {difficulty}. Ensure math is in LaTeX."
            
            try:
                # Request structured JSON matching our Pydantic schema
                response = client.chat(
                    model=MODEL_NAME,
                    messages=[{'role': 'user', 'content': prompt}],
                    format=GeneratedQuestionSchema.model_json_schema(),
                )
                
                # Strict Pydantic Validation
                content = response['message']['content']
                q_data = GeneratedQuestionSchema.model_validate_json(content)
                
                # Store new question in DB
                new_q = Question(
                    subject=q_data.subject,
                    topic=q_data.topic,
                    sub_topic=q_data.sub_topic,
                    difficulty_level=q_data.difficulty_level,
                    question_text=q_data.question_text,
                    options=q_data.options,
                    correct_option=q_data.correct_option,
                    concept_used=q_data.concept_used,
                    step_by_step_solution=q_data.step_by_step_solution,
                    common_trap=q_data.common_trap,
                    is_ai_generated=True
                )
                db.add(new_q)
                db.commit()
            except ValidationError as e:
                print(f"LLM output validation failed: {e}")
                db.rollback()
            except Exception as e:
                print(f"Generation error: {e}")
                db.rollback()
    finally:
        db.close()


def solve_doubt(attempt_id: int, user_query: str) -> str:
    """Uses MCP tool to fetch context and solve doubt via RAG."""
    db = SessionLocal()
    try:
        attempt = db.query(AttemptLedger).filter(AttemptLedger.id == attempt_id).first()
        if not attempt:
            return "Attempt not found in ledger."
        
        # Invoke MCP tool
        context = retrieve_question_context(attempt.question_id)
        
        prompt = (
            f"You are an elite JEE Tutor. The student has a doubt.\n\n"
            f"Context of the question:\n{context}\n\n"
            f"Student's query: {user_query}\n\n"
            f"Did the student get this correct?: {attempt.is_correct}\n\n"
            f"Please explain exactly why their logic failed or clarify their doubt. Use LaTeX formatting for all math."
        )
        
        response = client.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return response['message']['content']
    finally:
        db.close()
