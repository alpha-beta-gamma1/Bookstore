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
        genai.configure(api_key="AIzaSyCJxQsH_U1-zVNLnm-CKdbaVvx8ZPGoYhg")
        self.llm_model = genai.GenerativeModel('gemini-2.0-flash')

        self.entity_prompt = """
        Bạn là một trợ lý phân tích ngôn ngữ tự nhiên.    
        Yêu cầu: Trích xuất các thực thể từ câu sau:
        - "book_title": tên sách
        - "quantity": số lượng
        - "customer_name": tên khách hàng
        - "phone": số điện thoại
        - "address": địa chỉ
        - Nếu có NHIỀU sách: "books" là array
        - Nếu chỉ có 1 sách: "book_title" và "quantity" riêng biệt

        Trả về JSON duy nhất theo format:
        Format cho nhiều sách:
        {{
        "entities": {{
            "books": [
                {{"title": "sách 1", "quantity": 2}},
                {{"title": "sách 2", "quantity": 3}}
            ],
            "customer_name": null,
            "phone": null,
            "address": null
        }}
        }}

        Format cho 1 sách:
        {{
        "entities": {{
            "book_title": "tên sách",
            "quantity": "...",
            "customer_name": null,
            "phone": null,
            "address": null
        }}
        }}
        Câu cần phân tích: "{user_input}"
        """

    # ---------- Step 1: detect intent bằng embedding ----------
    def classify_intent(self, text: str, threshold: float = 0.1):
        user_emb = self.embed_model.encode(text, convert_to_tensor=True)
        best_intent, best_score = None, -1

        for intent, examples_emb in self.intent_embeddings.items():
            cos_scores = util.cos_sim(user_emb, examples_emb)
            max_score = torch.max(cos_scores).item()
            if max_score > best_score:
                best_intent, best_score = intent, max_score

        if best_score < threshold:
            return "unknown", best_score
        
        return best_intent, best_score

    # ---------- Step 2: extract entities bằng LLM với fallback ----------
    def extract_entities(self, text: str):
        prompt = self.entity_prompt.format(user_input=text)
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                response = self.llm_model.generate_content(prompt)
                json_str = response.text.strip().strip('`').replace("json", "").strip()
                return json.loads(json_str).get("entities", {})
            except Exception as e:
                print(f"LLM parse error (attempt {attempt + 1}/{max_retries}):", e)
                if attempt == max_retries - 1:
                    # Fallback: dùng regex để extract cơ bản
                    return self._fallback_entity_extraction(text)
        return {}
    
    def _fallback_entity_extraction(self, text: str):
        """Fallback khi LLM fail - extract entities bằng regex"""
        entities = {}
        
        # Extract số lượng
        qty_match = re.search(r'\b(\d+)\s*(?:cuốn|quyển|cái)', text, re.IGNORECASE)
        if qty_match:
            entities['quantity'] = int(qty_match.group(1))
        
        # Extract phone
        phone_match = re.search(r'\b0\d{9,10}\b', text)
        if phone_match:
            entities['phone'] = phone_match.group()
        
        # Extract tên sách phổ biến
        common_books = ['đắc nhân tâm', 'nhà giả kim', 'sapiens', 'atomic habits', 
                       'think and grow rich', 'rich dad poor dad', 'tuổi trẻ đáng giá bao nhiêu',
                       'sống thực tế giữa đời thực dụng', 'nghệ thuật tinh tế của việc đếch quan tâm']
        text_lower = text.lower()
        for book in common_books:
            if book in text_lower:
                entities['book_title'] = book
                break
        
        # Nếu không có book_title nhưng có số lượng, thử extract tên từ pattern
        if 'book_title' not in entities:
            # Pattern: "3 [tên sách]" hoặc "mua [tên sách]"
            patterns = [
                r'(?:mua|đặt|order)\s+(?:\d+\s+)?(.+?)(?:\s+và|\s*$)',
                r'\d+\s+(.+?)(?:\s+và|\s*$)'
            ]
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    potential_title = match.group(1).strip()
                    if len(potential_title) > 3:  # Tránh extract quá ngắn
                        entities['book_title'] = potential_title
                        break
        
        print(f"Fallback extraction: {entities}")
        return entities

    # ---------- Step 3: hàm tổng hợp ----------
    def analyze(self, text: str):
        intent, score = self.classify_intent(text)
        entities = {}
        # chỉ trích xuất entity khi intent cần
        if intent in ["order_book", "search_book"]:
            entities = self.extract_entities(text)
        return {
            "intent": intent,
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