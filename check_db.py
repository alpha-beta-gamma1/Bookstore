from bot.db import Database

db = Database("bookstore.db")

print("📚 Danh sách bảng và dữ liệu:")
db.show_all_tables()
