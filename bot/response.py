from typing import Dict, List, Optional
from bot.db import Database
from bot.dialog_manager import DialogManager
from bot.nlu import NLU
import unicodedata
import re


class ResponseGenerator:
    def __init__(self):
        self.db = Database()
        self.dialog_manager = DialogManager()
        self.nlu = NLU()

    def generate_response(self, session_id: str, user_message: str) -> str:
        """Tạo phản hồi cho người dùng. - Phân tích intent + entities một lần.
        - Xử lý đặc biệt nếu đang trong order flow (có thể exit bằng 'hủy' hoặc 'bye').
        """
        # Chuẩn hóa input để check nhanh
        msg_lower = user_message.lower().strip()

        # NLU: phân tích intent và entities **chỉ một lần**
        intent, _ = self.nlu.classify_intent(user_message)
        entities_result = self.nlu.analyze(user_message)
        entities = entities_result.get('entities', {}) if isinstance(entities_result, dict) else {}

        # Lấy trạng thái hiện tại
        state = self.dialog_manager.get_state(session_id)
        context = self.dialog_manager.get_context(session_id) or {}

        # print(f"Intent: {intent} (conf={intent_conf}), Entities: {entities}, State: {state}")

        # Nếu đang trong order flow, ưu tiên xử lý luồng đặt hàng
        if state and state.startswith('order_'):
            # Các từ khóa thoát rộng hơn
            exit_keywords = ['hủy', 'thôi', 'không mua', 'dừng', 'stop', 'cancel', 'tạm biệt', 'bye']
            if any(word in msg_lower for word in exit_keywords) :
                self.dialog_manager.clear_session(session_id)
                return "Đã hủy đặt hàng. Bạn cần gì khác không ạ?"

            # Nếu user nói 'thanks'/'cảm ơn' -> trả lời lịch sự nhưng vẫn để trong luồng
            if intent == 'thanks' or any(k in msg_lower for k in ['cảm ơn', 'thank you']):
                return "Rất vui được giúp đỡ bạn! Bạn còn cần gì cho đơn hàng không ạ?"

            # Xử lý luồng đặt hàng
            response = self._handle_order_flow(session_id, user_message, state, context, entities)
        else:
            # Không trong order flow -> xử lý theo intent bình thường
            if intent == 'greeting':
                response = self._handle_greeting()
            elif intent == 'search_book':
                response = self._handle_search_book(entities)
            elif intent == 'order_book':
                response = self._handle_start_order(session_id, user_message, entities)
            elif intent == 'list_books':
                response = self._handle_list_books()
            elif intent == 'thanks':
                response = "Rất vui được giúp đỡ bạn! Nếu cần thêm gì, đừng ngần ngại hỏi nhé!"
            elif intent == 'bye':
                response = "Tạm biệt! Hẹn gặp lại bạn!"
            else:
                response = self._handle_unknown()

        # Lưu lịch sử hội thoại, không để lỗi DB làm sập bot
        try:
            self.db.save_conversation(session_id, user_message, response, intent)
        except Exception as e:
            print(f"Warning: Lưu lịch sử thất bại: {e}")

        return response

    # ---------------- Handlers căn bản ----------------
    def _handle_greeting(self) -> str:
        return ("Xin chào! 👋 Tôi là trợ lý của BookStore.\n"
                "Tôi có thể giúp bạn:\n"
                "• Tìm sách: 'Tìm sách [tên sách]'\n"
                "• Đặt sách: 'Tôi muốn mua [tên sách]'\n"
                "• Xem danh sách: 'Có những sách gì'\n"
                "Bạn cần gì ạ?")

    def _handle_search_book(self, entities: Dict) -> str:
        book_title = entities.get('book_title') or ''
        keyword = str(book_title).strip() if book_title else ''
        if not keyword:
            return "Bạn muốn tìm sách gì ạ? Vui lòng cho biết tên sách."

        books = self.db.search_books(keyword)
        if not books:
            return (f"Xin lỗi, tôi không tìm thấy sách nào với từ khóa '{keyword}'. "
                    f"Bạn có thể xem danh sách sách bằng cách hỏi 'Có những sách gì?'")

        if len(books) == 1:
            book = books[0]
            return (f"📚 **{book['title']}**\n"
                    f"👤 Tác giả: {book['author']}\n"
                    f"💰 Giá: {book['price']:,.0f}đ\n"
                    f"📦 Còn lại: {book['stock']} cuốn\n"
                    f"🏷️ Thể loại: {book['category']}\n\n"
                    f"Nếu muốn đặt mua, bạn có thể nói 'Tôi muốn mua {book['title']}'")
        else:
            # Lưu danh sách kết quả tạm thời vào session để người dùng có thể chọn
            short_list = books[:10]
            candidates = {str(i+1): book['id'] for i, book in enumerate(short_list)}
            ctx = {'candidates': candidates, 'candidate_list_preview': short_list}
            # cập nhật state để chờ chọn sách
            # Lưu state 'order_choose_book' để người dùng chọn bằng số
            # Lưu context tạm để sử dụng khi chọn
            # dialog_manager.update_session được giả sử tồn tại
            self.dialog_manager.update_session_temp_context(ctx)

            response = f"Tôi tìm thấy {len(books)} kết quả. Vui lòng chọn số tương ứng (1-{len(short_list)}) hoặc viết rõ tên sách:\n\n"
            for i, book in enumerate(short_list, 1):
                response += (f"{i}. **{book['title']}** - {book['author']} | Giá: {book['price']:,.0f}đ | Còn: {book['stock']}\n")
            if len(books) > len(short_list):
                response += f"\n... và {len(books) - len(short_list)} kết quả khác."
            response += "\n\nBạn chọn số mấy?"
            # Set temporary state so next message is processed as choosing a book
            self.dialog_manager.update_session(session_id, state='order_choose_book', context=ctx)
            return response

    def _handle_list_books(self) -> str:
        books = self.db.get_all_books()
        if not books:
            return "Hiện tại cửa hàng chưa có sách nào."

        response = "📚 **DANH SÁCH SÁCH CỦA CỬA HÀNG:**\n\n"
        for book in books[:10]:
            response += (f"• **{book['title']}**\n"
                         f"  Tác giả: {book['author']} | Giá: {book['price']:,.0f}đ | Còn: {book['stock']} cuốn\n\n")

        if len(books) > 10:
            response += f"\n... và {len(books) - 10} cuốn sách khác."

        return response

    # ---------------- Khởi tạo order ----------------
    def _handle_start_order(self, session_id: str, user_message: str, entities: Dict) -> str:
        book_title = entities.get('book_title') or ''
        keyword = str(book_title).strip() if book_title else ''
        if not keyword:
            return "Bạn muốn mua sách gì ạ? Vui lòng cho biết tên sách."

        books = self.db.search_books(keyword)
        print("📚 Kết quả tìm sách:", books)

        if not books:
            return f"Xin lỗi, tôi không tìm thấy sách '{keyword}'. Vui lòng kiểm tra lại tên sách."

        if len(books) > 1:
            # Nếu nhiều kết quả -> delegate cho handler tìm kiếm để lưu state và chờ chọn
            return self._handle_search_book({'book_title': keyword})

        # 1 kết quả
        book = books[0]
        if book['stock'] == 0:
            return f"Xin lỗi, sách '{book['title']}' hiện đã hết hàng."

        # Chuẩn hoá và validate các entities nếu có
        quantity = self._normalize_and_validate_quantity(entities.get('quantity'), book['stock'])
        customer_name = self._validate_name(entities.get('customer_name'))
        phone = self._validate_phone(entities.get('phone'))
        address = self._validate_address(entities.get('address'))

        context = {
            'book_id': book['book_id'],
            'book_title': book['title'],
            'book_price': book['price'],
            'book_stock': book['stock'],
            'quantity': quantity,
            'customer_name': customer_name,
            'phone': phone,
            'address': address
        }

        missing = [f for f, v in [('quantity', quantity), ('customer_name', customer_name), ('phone', phone), ('address', address)] if not v]

        print(f"DEBUG - Missing fields: {missing}")
        print(f"DEBUG - Context: {context}")

        if not missing:
            total = context['book_price'] * context['quantity']
            self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
            return (f"📋 **XÁC NHẬN ĐƠN HÀNG:**\n\n"
                    f"📚 Sách: {context['book_title']}\n"
                    f"🔢 Số lượng: {context['quantity']} cuốn\n"
                    f"💰 Tổng tiền: {total:,.0f}đ\n"
                    f"👤 Người nhận: {context['customer_name']}\n"
                    f"📞 SĐT: {context['phone']}\n"
                    f"📍 Địa chỉ: {context['address']}\n\n"
                    f"Gõ 'xác nhận' để hoàn tất đặt hàng, 'sửa <trường>' để chỉnh, hoặc 'hủy' để hủy bỏ.")
        else:
            # Hỏi thông tin thiếu đầu tiên
            next_field = missing[0]
            next_state = f'order_ask_{next_field}'
            self.dialog_manager.update_session(session_id, state=next_state, context=context)
            questions = {
                'quantity': f"Bạn muốn mua mấy cuốn ạ? (Còn lại: {book['stock']} cuốn)",
                'customer_name': "Mình có thể biết tên của bạn không?",
                'phone': "Bạn cho mình xin số điện thoại để liên hệ nhé?",
                'address': "Bạn vui lòng cung cấp địa chỉ giao hàng?"
            }
            return questions[next_field]

    # ---------------- Luồng đặt hàng chi tiết ----------------
    def _handle_order_flow(self, session_id: str, message: str, state: str, context: Dict, entities: Dict = None) -> str:
        """Xử lý từng bước của luồng đặt hàng.
        - Hỗ trợ chọn sách khi state == 'order_choose_book'
        - Hỗ trợ sửa trong confirm: 'sửa số lượng 3', 'sửa địa chỉ ...'
        """
        msg_lower = message.lower()
        intent, _ = self.nlu.classify_intent(message)
        # Nếu entities không có, parse lại
        if entities is None:
            entities_res = self.nlu.analyze(message)
            entities = entities_res.get('entities', {}) if isinstance(entities_res, dict) else {}

        # Chọn sách từ danh sách tạm
        if state == 'order_choose_book':
            # context có 'candidates' mapping '1'->book_id
            candidates = context.get('candidates') if context else None
            if not candidates:
                # Fallback: clear and yêu cầu tìm lại
                self.dialog_manager.clear_session(session_id)
                return "Xin lỗi, danh sách lựa chọn đã hết hạn. Bạn vui lòng tìm lại sách nhé."

            # Thử lấy chỉ số
            idx_match = re.search(r'\b(\d{1,2})\b', message)
            if idx_match:
                idx = idx_match.group(1)
                book_id = candidates.get(idx)
                if book_id:
                    book = self.db.get_book_by_id(book_id)
                    if not book:
                        return "Không tìm thấy sách đã chọn, vui lòng thử lại."
                    # Tiếp tục quy trình với sách được chọn
                    # Cập nhật context giống như _handle_start_order
                    new_context = {
                        'book_id': book['book_id'],
                        'book_title': book['title'],
                        'book_price': book['price'],
                        'book_stock': book['stock'],
                        'quantity': None,
                        'customer_name': None,
                        'phone': None,
                        'address': None
                    }
                    self.dialog_manager.update_session(session_id, state='order_ask_quantity', context=new_context)
                    return f"Bạn đã chọn **{book['title']}**. Bạn muốn mua mấy cuốn? (Còn lại: {book['stock']})"
                else:
                    return "Số bạn chọn không có trong danh sách, vui lòng chọn lại."
            else:
                # Thử match theo tên ngắn
                # So sánh đơn giản: tìm sách có tên chứa message
                preview = context.get('candidate_list_preview', [])
                for b in preview:
                    if message.strip().lower() in b['title'].lower():
                        new_context = {
                            'book_id': b['book_id'],
                            'book_title': b['title'],
                            'book_price': b['price'],
                            'book_stock': b['stock'],
                            'quantity': None,
                            'customer_name': None,
                            'phone': None,
                            'address': None
                        }
                        self.dialog_manager.update_session(session_id, state='order_ask_quantity', context=new_context)
                        return f"Bạn đã chọn **{b['title']}**. Bạn muốn mua mấy cuốn? (Còn lại: {b['stock']})"
                return "Mình không hiểu lựa chọn của bạn — vui lòng chọn theo số (ví dụ: 1) hoặc viết rõ tên sách."

        # Các bước hỏi thông tin
        new_context = dict(context)

        if state == 'order_ask_quantity':
            qty = self._normalize_and_validate_quantity(entities.get('quantity') or None, context['book_stock'])
            if not qty:
                qty = self._extract_quantity_from_message(message, context['book_stock'])
                if not qty:
                    return f"Bạn muốn mua bao nhiêu cuốn? (Còn lại: {context['book_stock']} cuốn)"

            new_context['quantity'] = qty
            self.dialog_manager.update_session(session_id, state='order_ask_customer_name', context=new_context)
            return "Mình có thể biết tên của bạn không?"

        elif state == 'order_ask_customer_name':
            name = self._validate_name(entities.get('customer_name') or message.strip())
            if not name:
                return "Tên quá ngắn, bạn nhập lại giúp mình nhé!"

            new_context['customer_name'] = name
            self.dialog_manager.update_session(session_id, state='order_ask_phone', context=new_context)
            return "Bạn cho mình xin số điện thoại để liên hệ nhé?"

        elif state == 'order_ask_phone':
            phone = self._validate_phone(entities.get('phone') or self._extract_phone_from_message(message))
            if not phone:
                return "Số điện thoại không hợp lệ, vui lòng nhập lại (10-11 số)."

            new_context['phone'] = phone
            self.dialog_manager.update_session(session_id, state='order_ask_address', context=new_context)
            return "Bạn vui lòng cung cấp địa chỉ giao hàng?"

        elif state == 'order_ask_address':
            address = self._validate_address(entities.get('address') or message.strip())
            if not address:
                return "Địa chỉ hơi ngắn, bạn nhập chi tiết hơn nhé!"

            new_context['address'] = address
            total = new_context['book_price'] * new_context['quantity']
            self.dialog_manager.update_session(session_id, state='order_confirm', context=new_context)
            return (f"📋 **XÁC NHẬN ĐƠN HÀNG:**\n\n"
                    f"📚 Sách: {new_context['book_title']}\n"
                    f"🔢 Số lượng: {new_context['quantity']} cuốn\n"
                    f"💰 Tổng tiền: {total:,.0f}đ\n"
                    f"👤 Người nhận: {new_context['customer_name']}\n"
                    f"📞 SĐT: {new_context['phone']}\n"
                    f"📍 Địa chỉ: {new_context['address']}\n\n"
                    f"Gõ 'xác nhận' để hoàn tất đặt hàng, 'sửa <trường>' để sửa (ví dụ 'sửa số lượng 2'), hoặc 'hủy' để hủy đơn.")

        elif state == 'order_confirm':
            # Nếu user muốn sửa 1 trường: hỗ trợ 'sửa số lượng 3', 'sửa địa chỉ ...', 'sửa sđt 012...'
            edit_match = re.search(r"sửa\s+(số lượng|sl|sđt|sdt|số điện thoại|địa chỉ|tên)\s*(.*)", message.lower())
            if edit_match:
                field = edit_match.group(1)
                rest = edit_match.group(2).strip()
                if field in ['số lượng', 'sl']:
                    new_qty = self._normalize_and_validate_quantity(rest or None, context['book_stock']) or self._extract_quantity_from_message(rest or '', context['book_stock'])
                    if not new_qty:
                        return f"Số lượng không hợp lệ hoặc vượt quá tồn kho ({context['book_stock']}), vui lòng nhập lại."
                    context['quantity'] = new_qty
                    self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
                    total = context['quantity'] * context['book_price']
                    return f"Đã cập nhật số lượng thành {new_qty}. Tổng tiền mới: {total:,.0f}đ. Gõ 'xác nhận' để hoàn tất."
                if field in ['sđt', 'sdt', 'số điện thoại']:
                    phone = self._validate_phone(rest)
                    if not phone:
                        return "Số điện thoại không hợp lệ (10-11 chữ số)."
                    context['phone'] = phone
                    self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
                    return "Đã cập nhật số điện thoại. Vui lòng gõ 'xác nhận' để hoàn tất."
                if field == 'địa chỉ':
                    addr = self._validate_address(rest or '')
                    if not addr:
                        return "Địa chỉ quá ngắn, vui lòng nhập chi tiết hơn."
                    context['address'] = addr
                    self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
                    return "Đã cập nhật địa chỉ. Vui lòng gõ 'xác nhận' để hoàn tất."
                if field == 'tên':
                    name = self._validate_name(rest or '')
                    if not name:
                        return "Tên quá ngắn, vui lòng nhập lại."
                    context['customer_name'] = name
                    self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
                    return "Đã cập nhật tên người nhận. Vui lòng gõ 'xác nhận' để hoàn tất."

            # Xác nhận đơn
            if intent == "confirm_order" or any(word in msg_lower for word in ["xác nhận", "xac nhan", "ok", "đồng ý", "dong y"]):
    # tạo order

                order_data = {
                    'customer_name': context['customer_name'],
                    'phone': context['phone'],
                    'address': context['address'],
                    'book_id': context['book_id'],
                    'quantity': context['quantity']
                }
                try:
                    order_id = self.db.create_order(order_data)
                except Exception as e:
                    print(f"Error khi tạo đơn: {e}")
                    return "Có lỗi khi tạo đơn hàng, vui lòng thử lại sau."
                self.dialog_manager.clear_session(session_id)
                return (f"✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                        f"Mã đơn hàng: #{order_id}\n"
                        f"Chúng tôi sẽ liên hệ với bạn qua số {context['phone']} để xác nhận.\n"
                        f"Cảm ơn bạn đã mua sách tại BookStore! 🎉")

            # Nếu user muốn sửa toàn bộ: 'tôi muốn thay đổi' hoặc trả lời khác
            if any(k in msg_lower for k in ['sửa', 'thay', 'đổi']):
                return "Bạn muốn sửa trường nào? (số lượng, tên, sđt, địa chỉ) — ví dụ: 'sửa số lượng 2'"

            return "Vui lòng gõ 'xác nhận' để hoàn tất hoặc 'sửa <trường>' để chỉnh thông tin, 'hủy' để huỷ đơn."

        return "Có lỗi xảy ra. Vui lòng thử lại."

    # ---------------- Helper validation / parsing ----------------
    def _normalize_and_validate_quantity(self, quantity, max_stock: int) -> Optional[int]:
        """Chấp nhận int, chuỗi số, hoặc None. Trả về int hợp lệ hoặc None."""
        if quantity is None:
            return None
        # Nếu là string chứa chữ, thử lấy số
        if isinstance(quantity, str):
            quantity = quantity.strip()
            if quantity.isdigit():
                try:
                    q = int(quantity)
                except Exception:
                    return None
            else:
                # thử extract số từ chuỗi
                nums = re.findall(r"\d+", quantity)
                q = int(nums[0]) if nums else None
        elif isinstance(quantity, (int,)):
            q = quantity
        else:
            # thử ép kiểu số nếu có thể
            try:
                q = int(quantity)
            except Exception:
                return None

        if not isinstance(q, int) or q <= 0:
            return None
        if q > max_stock:
            return None
        return q

    def _validate_quantity(self, quantity, max_stock):
        # Bảo lưu (không dùng trực tiếp) - giữ cho backward compat
        return self._normalize_and_validate_quantity(quantity, max_stock)

    def _validate_name(self, name):
        if not name:
            return None
        s = str(name).strip()
        if len(s) < 2:
            return None
        return s

    def _validate_phone(self, phone):
        if not phone:
            return None
        phone_str = str(phone).strip()
        # Lấy only digits
        digits = re.findall(r"\d+", phone_str)
        phone_only = ''.join(digits)
        if len(phone_only) not in [10, 11]:
            return None
        if not phone_only.isdigit():
            return None
        return phone_only

    def _validate_address(self, address):
        if not address:
            return None
        addr = str(address).strip()
        if len(addr) < 5:
            return None
        return addr

    def _extract_phone_from_message(self, message):
        match = re.search(r"(\d{10,11})", message)
        return match.group() if match else None

    def _extract_quantity_from_message(self, message, max_stock):
        numbers = re.findall(r"\d+", message)
        for num_str in numbers:
            try:
                num = int(num_str)
                if 1 <= num <= max_stock:
                    return num
            except ValueError:
                continue
        return None

    def _handle_unknown(self) -> str:
        return ("Xin lỗi, tôi không hiểu yêu cầu của bạn. 😅\n"
                "Bạn có thể:\n"
                "• Tìm sách: 'Tìm sách [tên sách]'\n"
                "• Đặt sách: 'Tôi muốn mua [tên sách]'\n"
                "• Xem danh sách: 'Có những sách gì'")
