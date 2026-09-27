from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
import os

app = FastAPI(title="pawnshop")
engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./pawn.db"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/items/{item_id}")
def get_item(item_id: int):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, name, price FROM items WHERE id = :id"), {"id": item_id}).first()
    if row is None:
        raise HTTPException(status_code=404)
    return dict(row._mapping)
