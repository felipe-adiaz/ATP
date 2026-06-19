from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import pdf, trilha, perfil, drive

app = FastAPI(title="StudyFlow Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, trocar pelo domínio do Lovable
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pdf.router, prefix="/pdf", tags=["PDF"])
app.include_router(trilha.router, prefix="/trilha", tags=["Trilha"])
app.include_router(perfil.router, prefix="/perfil", tags=["Perfil"])
app.include_router(drive.router, prefix="/drive", tags=["Drive"])


@app.get("/")
def health():
    return {"status": "ok", "version": "0.1.0"}
