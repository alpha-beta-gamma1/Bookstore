import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import unicodedata
import re

def normalize_text(text: str) -> str:
    """Chuẩn hóa và bỏ dấu tiếng Việt"""
    if not text:
        return ""
    # chuẩn hoá unicode
    text = unicodedata.normalize("NFD", text)
    # bỏ dấu
    text = re.sub(r"[\u0300-\u036f]", "", text)
    return text.lower().strip()

class Database:
    def __init__(self, db_path='bookstore.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Tạo kết nối đến database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Khởi tạo database với schema"""
        with open('data/schema.sql', 'r', encoding='utf-8') as f:
            schema = f.read()
        
        conn = self.get_connection()
        conn.executescript(schema)
        conn.commit()
        conn.close()
    
    def search_books(self, keyword: str) -> List[Dict]:
        """Tìm sách theo từ khóa (không phân biệt hoa/thường, bỏ dấu)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books")
        rows = cursor.fetchall()
        conn.close()

        keyword_norm = normalize_text(keyword)
        books = []

        for row in rows:
            title_norm = normalize_text(row["title"])
            author_norm = normalize_text(row["author"])
            category_norm = normalize_text(row["category"])

            if (keyword_norm in title_norm
                or keyword_norm in author_norm
                or keyword_norm in category_norm):
                books.append(dict(row))

        return books
    
    def get_book_by_id(self, book_id: int) -> Optional[Dict]:
        """Lấy thông tin sách theo ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM books WHERE book_id = ?", (book_id,))
        row = cursor.fetchone()
        
        conn.close()
        return dict(row) if row else None
    
    def get_all_books(self) -> List[Dict]:
        """Lấy tất cả sách"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM books")
        books = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return books
    
    def create_order(self, order_data: Dict) -> int:
        """Tạo đơn hàng mới"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tính tổng tiền
        book = self.get_book_by_id(order_data['book_id'])
        total_price = book['price'] * order_data['quantity']
        
        query = """
        INSERT INTO orders (customer_name, phone, address, book_id, quantity, total_price)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (
            order_data['customer_name'],
            order_data['phone'],
            order_data['address'],
            order_data['book_id'],
            order_data['quantity'],
            total_price
        ))
        
        # Cập nhật số lượng tồn kho
        cursor.execute(
            "UPDATE books SET stock = stock - ? WHERE book_id = ?",
            (order_data['quantity'], order_data['book_id'])
        )
        
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        
        return order_id
    
    def show_table(self, table_name: str):
        """In toàn bộ dữ liệu trong 1 bảng"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            print(dict(row))
        return [dict(row) for row in rows]

    def show_all_tables(self):
        """In dữ liệu của tất cả các bảng"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        conn.close()

        for table in tables:
            print(f"\n===== {table.upper()} =====")
            self.show_table(table)

    
    def save_conversation(self, session_id: str, user_message: str, 
                         bot_response: str, intent: str):
        """Lưu lịch sử hội thoại"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
        INSERT INTO conversations (session_id, user_message, bot_response, intent)
        VALUES (?, ?, ?, ?)
        """
        
        cursor.execute(query, (session_id, user_message, bot_response, intent))
        conn.commit()
        conn.close()