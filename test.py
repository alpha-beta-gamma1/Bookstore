from bot.response import ResponseGenerator

def main():
    rg = ResponseGenerator()
    session_id = "test_008"

    while True:
        user_message = input("Bạn: ")
        if user_message.lower() in ["exit", "quit"]:
            print("👉 Thoát chương trình.")
            break

        response = rg.generate_response(session_id, user_message)
        print("Bot:", response)

if __name__ == "__main__":
    main()
