"""HTTP side of the tutor: one streaming chat endpoint."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import db, tutor
from app.web import get_course

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict]
    mode: str = "explain"
    concept: str | None = None
    attempt_id: str | None = None
    question_id: str | None = None


@router.post("/tutor/{course_id}/chat")
def chat(course_id: str, req: ChatRequest):
    course, errors = get_course(course_id)
    if errors:
        raise HTTPException(status_code=500, detail="Course has content errors")

    context, concept_id = "", req.concept
    if req.attempt_id and req.question_id:
        attempt = db.get_attempt(req.attempt_id)
        question = next((q for q in (attempt or {}).get("questions", []) if q["id"] == req.question_id), None)
        if question is None:
            raise HTTPException(status_code=404, detail="No such question in that attempt")
        answer = next((a for a in db.course_answers(course_id) if a["attempt_id"] == req.attempt_id and a["question_id"] == req.question_id), None)
        context = tutor.question_context(question, answer["chosen"] if answer else [])
        concept_id = concept_id or question["concept"]
    concept = course.concepts.get(concept_id) if concept_id else None

    def reply():
        try:
            yield from tutor.stream_reply(course, concept, req.mode, req.messages, context)
        except tutor.TutorError as e:
            # The response has already started, so errors are sent as text the chat panel shows
            yield f"\n\n⚠ {e}"

    # text/plain streamed chunk by chunk; the browser reads it with fetch() and shows it as it arrives
    return StreamingResponse(reply(), media_type="text/plain; charset=utf-8", headers={"X-Accel-Buffering": "no"})
