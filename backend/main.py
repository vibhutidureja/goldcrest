from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from typing import List
from database import get_db, engine, Base
import models
from schemas import (
    AnalyticsResponse, TopicAccuracy, TestGenerateRequest, 
    TestSubmitRequest, DoubtRequest, DoubtResponse, QuestionGeneratePrompt
)
from agent import generate_questions_for_topic, solve_doubt

# Auto-create tables (in production, use alembic migrations)
with engine.begin() as conn:
    # conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    pass
Base.metadata.create_all(bind=engine)

# Seed default user and dummy question so frontend works out of the box
db = SessionLocal()
if not db.query(models.User).filter(models.User.id == 1).first():
    db.add(models.User(id=1, email="student@goldcrest.edu", password_hash="hashed"))
if not db.query(models.Question).first():
    db.add(models.Question(
        subject="Physics",
        topic="Kinematics",
        sub_topic="1D Motion",
        difficulty_level=3,
        question_text="A car accelerates uniformly from rest to a speed of 20 m/s in 5 seconds. What is the acceleration?",
        options=["2 m/s²", "4 m/s²", "5 m/s²", "10 m/s²"],
        correct_option="4 m/s²",
        concept_used="Acceleration is the rate of change of velocity: $a = \\frac{v - u}{t}$",
        step_by_step_solution="1. Initial velocity $u = 0$\n2. Final velocity $v = 20$\n3. Time $t = 5$\n4. $a = \\frac{20 - 0}{5} = 4$ m/s²",
        common_trap="Using the formula for distance instead of acceleration.",
        is_ai_generated=False
    ))
db.commit()
db.close()

app = FastAPI(title="JEE MCQ Adaptive Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/analytics/{user_id}", response_model=AnalyticsResponse)
def get_analytics(user_id: int, db: Session = Depends(get_db)):
    """Calculate historical accuracy per topic based on AttemptLedger."""
    attempts = db.query(models.AttemptLedger).filter(models.AttemptLedger.user_id == user_id).all()
    
    topic_stats = {}
    for attempt in attempts:
        topic = attempt.question.topic
        if topic not in topic_stats:
            topic_stats[topic] = {"total": 0, "correct": 0}
        topic_stats[topic]["total"] += 1
        if attempt.is_correct:
            topic_stats[topic]["correct"] += 1
            
    strong_topics = []
    weak_topics = []
    
    for topic, stats in topic_stats.items():
        accuracy = (stats["correct"] / stats["total"]) * 100
        ta = TopicAccuracy(topic=topic, total_attempts=stats["total"], accuracy_percentage=accuracy)
        if accuracy >= 50.0:
            strong_topics.append(ta)
        else:
            weak_topics.append(ta)
            
    return AnalyticsResponse(user_id=user_id, strong_topics=strong_topics, weak_topics=weak_topics)


@app.post("/api/test/generate")
def generate_test(req: TestGenerateRequest, db: Session = Depends(get_db)):
    """Build a 20-question test weighing 70% toward the user's weak topics."""
    # Find weak topics for user
    analytics = get_analytics(req.user_id, db)
    weak_topic_names = [t.topic for t in analytics.weak_topics]
    
    questions = []
    
    # 70% of 20 = 14 questions from weak topics
    if weak_topic_names:
        weak_q = db.query(models.Question).filter(
            models.Question.topic.in_(weak_topic_names)
        ).order_by(func.random()).limit(14).all()
        questions.extend(weak_q)
    
    # 30% from any topic (or to fill remaining if not enough weak topics)
    remaining_limit = 20 - len(questions)
    if remaining_limit > 0:
        other_q = db.query(models.Question).order_by(func.random()).limit(remaining_limit).all()
        # Ensure we don't duplicate (in real implementation, avoid dupes properly)
        questions.extend(other_q)
        
    return {
        "questions": [{
            "id": q.id, 
            "subject": q.subject,
            "topic": q.topic,
            "text": q.question_text, 
            "options": q.options
        } for q in questions]
    }


@app.post("/api/test/submit")
def submit_test(req: TestSubmitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Submit test attempt and trigger async LLM agent to generate new questions for weak topics."""
    test_topic_stats = {}
    
    for attempt_data in req.attempts:
        # Log attempt
        attempt = models.AttemptLedger(
            user_id=req.user_id,
            question_id=attempt_data.question_id,
            is_correct=attempt_data.is_correct,
            time_taken_seconds=attempt_data.time_taken_seconds
        )
        db.add(attempt)
        
        # Track topics within this test session to find new weak spots
        q = db.query(models.Question).filter(models.Question.id == attempt_data.question_id).first()
        if q:
            if q.topic not in test_topic_stats:
                test_topic_stats[q.topic] = {"subject": q.subject, "total": 0, "correct": 0}
            test_topic_stats[q.topic]["total"] += 1
            if attempt_data.is_correct:
                test_topic_stats[q.topic]["correct"] += 1
                
    db.commit()
    
    # Dispatch non-blocking BackgroundTasks to generate questions for weak topics (< 50% accuracy)
    for topic, stats in test_topic_stats.items():
        accuracy = (stats["correct"] / stats["total"]) * 100
        if accuracy < 50.0:
            # Generate 2 new questions for this topic in the background
            background_tasks.add_task(generate_questions_for_topic, stats["subject"], topic, 3, 2)
            
    return {"status": "Test submitted successfully", "weak_topics_triggered": len([t for t, s in test_topic_stats.items() if (s["correct"]/s["total"])*100 < 50])}


@app.get("/api/test/review/{attempt_id}")
def review_test(attempt_id: int, db: Session = Depends(get_db)):
    """Returns the full detailed approach for a specific attempt."""
    attempt = db.query(models.AttemptLedger).filter(models.AttemptLedger.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    q = attempt.question
    return {
        "question_text": q.question_text,
        "options": q.options,
        "correct_option": q.correct_option,
        "step_by_step_solution": q.step_by_step_solution,
        "concept_used": q.concept_used,
        "common_trap": q.common_trap,
        "is_correct": attempt.is_correct,
        "time_taken_seconds": attempt.time_taken_seconds
    }


@app.post("/api/test/doubt", response_model=DoubtResponse)
def solve_student_doubt(req: DoubtRequest):
    """Utilizes MCP-integrated RAG system to solve student doubt based on the question context."""
    explanation = solve_doubt(req.attempt_id, req.user_query)
    return DoubtResponse(explanation=explanation)


@app.post("/api/admin/generate-questions")
def admin_generate_questions(req: QuestionGeneratePrompt, background_tasks: BackgroundTasks):
    """Admin endpoint to seed the database with new questions for a given topic."""
    # Generate 5 questions in the background
    background_tasks.add_task(generate_questions_for_topic, req.subject, req.topic, req.difficulty_level, 5)
    return {"status": "Generating 5 questions in the background", "subject": req.subject, "topic": req.topic}

