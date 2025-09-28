from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # add ./bot

from bot.response import ResponseGenerator
from bot.db import Database

# =====================================================
# FastAPI App Config
# =====================================================

app = FastAPI(
    title="📚 BookStore Chatbot API",
    version="1.0.0",
    description="API tương tác với Chatbot BookStore"
)

# CORS cho phép mọi origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# Service Instances
# =====================================================
response_generator = ResponseGenerator()
db = Database()

# =====================================================
# Models
# =====================================================

class ChatRequest(BaseModel):
    session_id: Optional[str] = "default"
    message: str

class ChatResponse(BaseModel):
    success: bool
    response: str
    session_id: str

class Book(BaseModel):
    book_id: int
    title: str
    author: str
    price: float
    stock: int
    category: str

class BookListResponse(BaseModel):
    success: bool
    total: int
    books: List[Book]

class SingleBookResponse(BaseModel):
    success: bool
    book: Book

# =====================================================
# API Endpoints
# =====================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "📚 BookStore Chatbot API đang chạy", "version": "1.0.0"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat API"""
    if not request.message:
        raise HTTPException(status_code=400, detail="message is required")
    try:
        response = response_generator.generate_response(
            request.session_id, request.message
        )
        return ChatResponse(success=True, response=response, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books", response_model=BookListResponse)
async def get_books():
    """Danh sách tất cả sách"""
    try:
        books = db.get_all_books()
        return {"success": True, "books": books, "total": len(books)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{book_id}", response_model=SingleBookResponse)
async def get_book(book_id: int):
    """Thông tin chi tiết một cuốn sách"""
    try:
        book = db.get_book_by_id(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        return {"success": True, "book": book}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search", response_model=BookListResponse)
async def search_books(q: str):
    """Tìm kiếm sách theo từ khóa"""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    try:
        books = db.search_books(q)
        return {"success": True, "books": books, "total": len(books)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Kiểm tra tình trạng"""
    return {"status": "healthy", "service": "BookStore Chatbot API"}

@app.get("/chat", response_class=HTMLResponse)
async def chat_interface():
    """Frontend Chat UI"""
    try:
        with open("app/chat.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h2>⚠️ Không tìm thấy chat.html, vui lòng tạo app/chat.html</h2>")