# import_books.py

import sqlite3
import csv

DB_PATH = "bookstore.db"

def import_books_from_csv(csv_file="data/books.csv"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO Books (title, author, price, stock, category)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(title, author) DO UPDATE SET
                    stock = Books.stock + excluded.stock
            """, (
                row["title"],
                row["author"],
                float(row["price"]),
                int(row["stock"]),
                row["category"]
            ))


    conn.commit()
    conn.close()
    print("✅ Imported books from CSV!")

if __name__ == "__main__":
    import_books_from_csv()