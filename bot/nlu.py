from sentence_transformers import SentenceTransformer, util
import torch
import google.generativeai as genai
import json
import re

class NLU:
    def __init__(self):
        # --------- Load embedding model ----------
        self.embed_model = SentenceTransformer("bkai-foundation-models/vietnamese-bi-encoder")

        # Intent mẫu
        self.intent_samples = {
            "greeting": [
                "xin chào", "chào bạn", "hello", "hi", "alo shop",
                "ê bạn", "shop ơi", "hí", "bạn ơi", "chào buổi sáng",
                "good morning", "good evening"
            ],
            "search_book": [
                "tìm sách", "có sách không", "giá sách", "thông tin sách",
                "sách này bao nhiêu", "cho mình hỏi sách", "tìm giúp quyển sách",
                "có bán quyển ... không", "mình muốn hỏi về sách",
                "sách tên ... có không", "mình cần thông tin sách"
            ],
            "order_book": [
                "muốn mua sách", "đặt sách", "order sách", "cho tôi mua",
                "mình muốn đặt mua", "lấy cho mình quyển này", "cho mình đặt",
                "ship sách này cho mình", "tôi muốn mua quyển ...", "chốt đơn giúp mình",
                "order quyển ...", "đặt mua quyển ...",
                "có", "ok", "chốt", "ừ", "yes", "đồng ý", "mình mua","1 cuốn"," 5 ","tôi tên "
                ,"tôi là ","tôi ở ","giao đến ","giao hàng đến ","số điện thoại ","địa chỉ ","số đt "
                ,"sđt "
            ],
            "list_books": [
                "danh sách sách", "có những sách gì", "xem sách",
                "shop có sách nào", "có loại nào", "show sách đi",
                "liệt kê sách giúp mình", "cho mình danh mục sách",
                "những quyển nào có ở shop"
            ],
            "check_stock": [
                "còn hàng", "còn bao nhiêu", "còn sách không",
                "hết hàng chưa", "còn quyển này không", "có còn tồn không",
                "stock còn không", "còn mấy cuốn", "còn bao nhiêu bản"
            ],
            "thanks": [
                "cảm ơn", "thanks", "thank you", "cám ơn",
                "thx", "thanks shop", "ok cảm ơn nhiều", "cảm ơn bạn nhiều"
            ],
            "confirm_order": [
                "xác nhận", "ok", "đồng ý", "chốt đơn", "ok chốt", "ok mình lấy",
                "mua luôn", "đặt luôn", "đồng ý mua", "oke", "okie"
            ],

            "bye": [
                "tạm biệt", "bye", "hẹn gặp lại",
                "see you", "goodbye", "cút đây", "gặp lại sau",
                "bye shop", "ok mình đi đây"
            ]
        }

        # Encode các ví dụ
        self.intent_embeddings = {
            intent: self.embed_model.encode(samples, convert_to_tensor=True)
            for intent, samples in self.intent_samples.items()
        }

        # --------- LLM Config (Gemini) ----------
        genai.configure(api_key="AIzaSyCJxQsH_U1-zVNLnm-CKdbaVvx8ZPGoYhg")  # đặt key thật
        self.llm_model = genai.GenerativeModel('gemini-2.0-flash')

        self.entity_prompt = """
        Bạn là một trợ lý phân tích ngôn ngữ tự nhiên.    
        Yêu cầu: Trích xuất các thực thể từ câu sau:
        - "book_title": tên sách
        - "quantity": số lượng
        - "customer_name": tên khách hàng
        - "phone": số điện thoại
        - "address": địa chỉ

        Trả về JSON duy nhất theo format:
        {{
        "entities": {{
            "book_title": "...",
            "quantity": 2,
            "customer_name": "...",
            "phone": "...",
            "address": "..."
        }}
        }}

        Câu cần phân tích: "{user_input}"
        """

    # ---------- Step 1: detect intent bằng embedding ----------
    def classify_intent(self, text: str, threshold: float = 0.15):
        user_emb = self.embed_model.encode(text, convert_to_tensor=True)
        best_intent, best_score = None, -1

        for intent, examples_emb in self.intent_embeddings.items():
            cos_scores = util.cos_sim(user_emb, examples_emb)
            max_score = torch.max(cos_scores).item()
            if max_score > best_score:
                best_intent, best_score = intent, max_score

        # 🔎 Nếu score nhỏ hơn threshold thì gán intent = "unknown"
        if best_score < threshold:
            return "unknown", best_score
        
        return best_intent, best_score


    # ---------- Step 2: extract entities bằng LLM ----------
    def extract_entities(self, text: str):
        prompt = self.entity_prompt.format(user_input=text)
        try:
            response = self.llm_model.generate_content(prompt)
            json_str = response.text.strip().strip('`').replace("json", "").strip()
            return json.loads(json_str).get("entities", {})
        except Exception as e:
            print("LLM parse error:", e)
            return {}

    # ---------- Step 3: hàm tổng hợp ----------
    def analyze(self, text: str):
        intent, score = self.classify_intent(text)
        entities = {}
        # chỉ trích xuất entity khi intent cần
        if intent in ["order_book", "search_book"]:
            entities = self.extract_entities(text)
        return {
            # "intent": intent,
            "confidence": score,
            "entities": entities
        }
    
    def extract_entities_with_fallback(self, text: str):
        """Extract entities với fallback regex cho các trường hợp đơn giản"""
        # Gọi LLM trước
        entities = self.extract_entities(text)
        
        # Fallback cho phone nếu LLM không extract được
        if not entities.get('phone'):
            phone_match = re.search(r'\b0\d{9,10}\b', text)
            if phone_match:
                entities['phone'] = phone_match.group()
        
        # Fallback cho quantity
        if not entities.get('quantity'):
            qty_match = re.search(r'\b(\d+)\s*(?:cuốn|quyển|cái|cục)\b', text, re.IGNORECASE)
            if qty_match:
                entities['quantity'] = int(qty_match.group(1))
        
        # Fallback cho customer_name (nếu message chỉ có tên)
        if not entities.get('customer_name') and len(text.strip().split()) <= 3:
            # Nếu message ngắn và không chứa số, có thể là tên
            if not re.search(r'\d', text) and len(text.strip()) >= 2:
                entities['customer_name'] = text.strip().title()
        
        return entities

# ---------------- DEMO -----------------
if __name__ == "__main__":
    nlu = NLU()
    while True:
        user_input = input("Bạn: ")
        if user_input.lower() in ["quit", "exit"]:
            break
        result = nlu.analyze(user_input)
        print("->", result)