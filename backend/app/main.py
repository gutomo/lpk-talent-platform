from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, conversation, health, interview, me, passport, speech, students

settings = get_settings()

app = FastAPI(title="LPK Talent Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(students.router)
app.include_router(speech.router)
app.include_router(conversation.router)
app.include_router(interview.router)
app.include_router(passport.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "lpk-talent-platform", "env": settings.app_env}
