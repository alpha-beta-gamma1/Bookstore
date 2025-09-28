import uvicorn
import sys
import os

# Thêm thư mục hiện tại vào Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Chạy server FastAPI
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )