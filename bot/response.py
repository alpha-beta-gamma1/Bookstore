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
        """Tạo phản hồi cho người dùng với hỗ trợ đặt nhiều sách"""
        msg_lower = user_message.lower().strip()

        # NLU: phân tích intent và entities
        intent, _ = self.nlu.classify_intent(user_message)
        entities_result = self.nlu.analyze(user_message)
        entities = entities_result.get('entities', {}) if isinstance(entities_result, dict) else {}

        # Lấy trạng thái hiện tại
        state = self.dialog_manager.get_state(session_id)
        context = self.dialog_manager.get_context(session_id) or {}

        print(f"Intent: {intent} , Entities: {entities}, State: {state}")

        # Nếu đang trong order flow
        if state and state.startswith('order_'):
            exit_keywords = ['hủy', 'thôi', 'không mua', 'dừng', 'stop', 'cancel', 'tạm biệt', 'bye']
            if any(word in msg_lower for word in exit_keywords):
                self.dialog_manager.clear_session(session_id)
                return "Đã hủy đặt hàng. Bạn cần gì khác không ạ?"

            if intent == 'thanks' or any(k in msg_lower for k in ['cảm ơn', 'thank you']):
                return "Rất vui được giúp đỡ bạn! Bạn còn cần gì cho đơn hàng không ạ?"

            response = self._handle_order_flow(session_id, user_message, state, context, entities)
        else:
            # Không trong order flow
            if intent == 'greeting':
                response = self._handle_greeting()
            elif intent == 'search_book':
                response = self._handle_search_book(entities)
            elif intent == 'order_book':
                # 🔥 FIX: Xử lý cả đơn sách và nhiều sách
                response = self._handle_start_order(session_id, user_message, entities)
            elif intent == 'list_books':
                response = self._handle_list_books()
            elif intent == 'thanks':
                response = "Rất vui được giúp đỡ bạn! Nếu cần thêm gì, đừng ngần ngại hỏi nhé!"
            elif intent == 'bye':
                response = "Tạm biệt! Hẹn gặp lại bạn!"
            else:
                response = self._handle_unknown()

        try:
            self.db.save_conversation(session_id, user_message, response, intent)
        except Exception as e:
            print(f"Warning: Lưu lịch sử thất bại: {e}")

        return response

    # ---------------- Handlers cơ bản ----------------
    def _handle_greeting(self) -> str:
        return ("Xin chào! 👋 Tôi là trợ lý của BookStore.\n"
                "Tôi có thể giúp bạn:\n"
                "• Tìm sách: 'Tìm sách [tên sách]'\n"
                "• Đặt sách: 'Tôi muốn mua [tên sách]'\n"
                "• Đặt nhiều sách: 'Mua 2 đắc nhân tâm và 3 nhà giả kim'\n"
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
            short_list = books[:10]
            candidates = {str(i+1): book['id'] for i, book in enumerate(short_list)}
            ctx = {'candidates': candidates, 'candidate_list_preview': short_list}

            response = f"Tôi tìm thấy {len(books)} kết quả. Vui lòng chọn số tương ứng (1-{len(short_list)}) hoặc viết rõ tên sách:\n\n"
            for i, book in enumerate(short_list, 1):
                response += (f"{i}. **{book['title']}** - {book['author']} | Giá: {book['price']:,.0f}đ | Còn: {book['stock']}\n")
            if len(books) > len(short_list):
                response += f"\n... và {len(books) - len(short_list)} kết quả khác."
            response += "\n\nBạn chọn số mấy?"
            
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

    # ---------------- 🔥 FIX: Xử lý đặt hàng nhiều sách ----------------
    def _handle_start_order(self, session_id: str, user_message: str, entities: Dict) -> str:
        """Xử lý đặt hàng - hỗ trợ cả 1 sách và nhiều sách"""
        
        # 🔥 Case 1: Nhiều sách (books array)
        if 'books' in entities and isinstance(entities['books'], list):
            return self._handle_multi_book_order(session_id, entities)
        
        # 🔥 Case 2: Một sách (book_title)
        book_title = entities.get('book_title') or ''
        keyword = str(book_title).strip() if book_title else ''
        if not keyword:
            return "Bạn muốn mua sách gì ạ? Vui lòng cho biết tên sách."

        books = self.db.search_books(keyword)

        if not books:
            return f"Xin lỗi, tôi không tìm thấy sách '{keyword}'. Vui lòng kiểm tra lại tên sách."

        if len(books) > 1:
            return self._handle_search_book({'book_title': keyword})

        # 1 kết quả
        book = books[0]
        if book['stock'] == 0:
            return f"Xin lỗi, sách '{book['title']}' hiện đã hết hàng."

        # Chuẩn hóa và validate
        quantity = self._normalize_and_validate_quantity(entities.get('quantity'), book['stock'])
        customer_name = self._validate_name(entities.get('customer_name'))
        phone = self._validate_phone(entities.get('phone'))
        address = self._validate_address(entities.get('address'))

        context = {
            'order_type': 'single',  # Đánh dấu đơn sách đơn
            'book_id': book['book_id'],
            'book_title': book['title'],
            'book_price': book['price'],
            'book_stock': book['stock'],
            'quantity': quantity,
            'customer_name': customer_name,
            'phone': phone,
            'address': address
        }

        return self._proceed_to_next_step(session_id, context)

    def _handle_multi_book_order(self, session_id: str, entities: Dict) -> str:
        """🔥 XỬ LÝ ĐẶT NHIỀU SÁCH CÙNG LÚC"""
        books_data = entities['books']
        
        # Validate và chuẩn bị thông tin các sách
        order_items = []
        total_price = 0
        errors = []
        
        for item in books_data:
            title = item.get('title', '').strip()
            qty = item.get('quantity', 1)
            
            if not title:
                continue
                
            # Tìm sách trong DB
            books = self.db.search_books(title)
            
            if not books:
                errors.append(f"❌ Không tìm thấy sách '{title}'")
                continue
            
            if len(books) > 1:
                errors.append(f"⚠️ Tìm thấy nhiều kết quả cho '{title}', vui lòng chọn rõ hơn")
                continue
            
            book = books[0]
            
            # Validate số lượng
            qty_validated = self._normalize_and_validate_quantity(qty, book['stock'])
            if qty_validated is None:
                errors.append(f"❌ Số lượng không hợp lệ cho '{book['title']}' (còn {book['stock']} cuốn)")
                continue
            
            order_items.append({
                'book_id': book['book_id'],
                'title': book['title'],
                'price': book['price'],
                'stock': book['stock'],
                'quantity': qty_validated
            })
            total_price += book['price'] * qty_validated
        
        # Kiểm tra có sách hợp lệ không
        if not order_items:
            error_msg = "Không thể xử lý đơn hàng:\n" + "\n".join(errors)
            return error_msg
        
        # Hiển thị thông báo lỗi nếu có
        warning = ""
        if errors:
            warning = "**LƯU Ý:**\n" + "\n".join(errors) + "\n\n"
        
        # Lưu context cho đơn hàng nhiều sách
        context = {
            'order_type': 'multi',
            'order_items': order_items,
            'total_price': total_price,
            'customer_name': entities.get('customer_name'),
            'phone': entities.get('phone'),
            'address': entities.get('address')
        }
        
        # 🔥 FIX: Không thêm summary ở đây nữa, để _proceed_to_next_step xử lý
        return (warning if warning else "") + self._proceed_to_next_step(session_id, context)

    def _proceed_to_next_step(self, session_id: str, context: dict) -> str:
        """Kiểm tra thông tin còn thiếu và chuyển đến bước tiếp theo"""
        required_fields = ['customer_name', 'phone', 'address']
        
        # Đối với đơn sách đơn, cần cả quantity
        if context.get('order_type') == 'single':
            required_fields.insert(0, 'quantity')
        
        missing = [f for f in required_fields if not context.get(f)]
        
        print(f"DEBUG - Missing fields: {missing}")
        
        if missing:
            next_field = missing[0]
            next_state = f'order_ask_{next_field}'
            self.dialog_manager.update_session(session_id, state=next_state, context=context)
            
            # 🔥 FIX: Hiển thị summary trước câu hỏi cho đơn nhiều sách
            prefix = ""
            if context.get('order_type') == 'multi' and next_field == 'customer_name':
                prefix = self._format_order_summary(context) + "\n\n"
            
            questions = {
                'quantity': f"Bạn muốn mua mấy cuốn ạ? (Còn lại: {context.get('book_stock', 0)} cuốn)",
                'customer_name': "Mình có thể biết tên của bạn không?",
                'phone': "Bạn cho mình xin số điện thoại để liên hệ nhé?",
                'address': "Bạn vui lòng cung cấp địa chỉ giao hàng?"
            }
            return prefix + questions[next_field]
        else:
            # Đủ thông tin -> xác nhận
            return self._generate_order_confirmation(session_id, context)
    
    def _format_order_summary(self, context: dict) -> str:
        """Format summary cho đơn nhiều sách"""
        if context.get('order_type') != 'multi':
            return ""
        
        summary = "📋 **ĐƠN HÀNG CỦA BẠN:**\n\n"
        for i, item in enumerate(context['order_items'], 1):
            subtotal = item['price'] * item['quantity']
            summary += f"{i}. **{item['title']}** x{item['quantity']} = {subtotal:,.0f}đ\n"
        
        summary += f"\n💰 **Tổng cộng: {context['total_price']:,.0f}đ**"
        return summary

    def _generate_order_confirmation(self, session_id: str, context: dict) -> str:
        """Tạo thông báo xác nhận đơn hàng"""
        self.dialog_manager.update_session(session_id, state='order_confirm', context=context)
        
        if context.get('order_type') == 'multi':
            # Đơn nhiều sách
            items_text = ""
            for i, item in enumerate(context['order_items'], 1):
                subtotal = item['price'] * item['quantity']
                items_text += f"  {i}. {item['title']} x{item['quantity']} = {subtotal:,.0f}đ\n"
            
            return (f"📋 **XÁC NHẬN ĐÔN HÀNG:**\n\n"
                    f"📚 Sách:\n{items_text}\n"
                    f"💰 Tổng tiền: {context['total_price']:,.0f}đ\n"
                    f"👤 Người nhận: {context['customer_name']}\n"
                    f"📞 SĐT: {context['phone']}\n"
                    f"📍 Địa chỉ: {context['address']}\n\n"
                    f"Gõ 'xác nhận' để hoàn tất đặt hàng, 'sửa <trường>' để chỉnh, hoặc 'hủy' để hủy bỏ.")
        else:
            # Đơn sách đơn
            total = context['book_price'] * context['quantity']
            return (f"📋 **XÁC NHẬN ĐƠN HÀNG:**\n\n"
                    f"📚 Sách: {context['book_title']}\n"
                    f"🔢 Số lượng: {context['quantity']} cuốn\n"
                    f"💰 Tổng tiền: {total:,.0f}đ\n"
                    f"👤 Người nhận: {context['customer_name']}\n"
                    f"📞 SĐT: {context['phone']}\n"
                    f"📍 Địa chỉ: {context['address']}\n\n"
                    f"Gõ 'xác nhận' để hoàn tất đặt hàng, 'sửa <trường>' để chỉnh, hoặc 'hủy' để hủy bỏ.")

    # ---------------- Luồng đặt hàng chi tiết ----------------
    def _handle_order_flow(self, session_id: str, message: str, state: str, context: Dict, entities: Dict = None) -> str:
        """Xử lý từng bước của luồng đặt hàng"""
        msg_lower = message.lower()
        intent, _ = self.nlu.classify_intent(message)
        
        if entities is None:
            entities_res = self.nlu.analyze(message)
            entities = entities_res.get('entities', {}) if isinstance(entities_res, dict) else {}

        # Chọn sách từ danh sách tạm
        if state == 'order_choose_book':
            candidates = context.get('candidates') if context else None
            if not candidates:
                self.dialog_manager.clear_session(session_id)
                return "Xin lỗi, danh sách lựa chọn đã hết hạn. Bạn vui lòng tìm lại sách nhé."

            idx_match = re.search(r'\b(\d{1,2})\b', message)
            if idx_match:
                idx = idx_match.group(1)
                book_id = candidates.get(idx)
                if book_id:
                    book = self.db.get_book_by_id(book_id)
                    if not book:
                        return "Không tìm thấy sách đã chọn, vui lòng thử lại."
                    
                    new_context = {
                        'order_type': 'single',
                        'book_id': book['book_id'],
                        'book_title': book['title'],
                        'book_price': book['price'],
                        'book_stock': book['stock'],
                        'quantity': None,
                        'customer_name': None,
                        'phone': None,
                        'address': None
                    }
                    return self._proceed_to_next_step(session_id, new_context)
                else:
                    return "Số bạn chọn không có trong danh sách, vui lòng chọn lại."
            else:
                preview = context.get('candidate_list_preview', [])
                for b in preview:
                    if message.strip().lower() in b['title'].lower():
                        new_context = {
                            'order_type': 'single',
                            'book_id': b['book_id'],
                            'book_title': b['title'],
                            'book_price': b['price'],
                            'book_stock': b['stock'],
                            'quantity': None,
                            'customer_name': None,
                            'phone': None,
                            'address': None
                        }
                        return self._proceed_to_next_step(session_id, new_context)
                return "Mình không hiểu lựa chọn của bạn – vui lòng chọn theo số (ví dụ: 1) hoặc viết rõ tên sách."

        # Các bước hỏi thông tin
        new_context = dict(context)

        if state == 'order_ask_quantity':
            qty_raw = entities.get('quantity') or self._extract_quantity_from_message(message, context['book_stock'])
            if qty_raw is None:
                return f"Bạn muốn mua bao nhiêu cuốn? (Còn lại: {context['book_stock']} cuốn)"

            qty = self._normalize_and_validate_quantity(qty_raw, context['book_stock'])
            if qty is None:
                return f"Số lượng bạn nhập ({qty_raw}) vượt quá tồn kho ({context['book_stock']} cuốn). Vui lòng chọn lại."

            new_context['quantity'] = qty
            return self._proceed_to_next_step(session_id, new_context)

        elif state == 'order_ask_customer_name':
            name = self._validate_name(entities.get('customer_name') or message.strip())
            if not name:
                return "Tên quá ngắn, bạn nhập lại giúp mình nhé!"

            new_context['customer_name'] = name
            return self._proceed_to_next_step(session_id, new_context)

        elif state == 'order_ask_phone':
            phone = self._validate_phone(entities.get('phone') or self._extract_phone_from_message(message))
            if not phone:
                return "Số điện thoại không hợp lệ, vui lòng nhập lại (10-11 số)."

            new_context['phone'] = phone
            return self._proceed_to_next_step(session_id, new_context)

        elif state == 'order_ask_address':
            address = self._validate_address(entities.get('address') or message.strip())
            if not address:
                return "Địa chỉ hơi ngắn, bạn nhập chi tiết hơn nhé!"

            new_context['address'] = address
            return self._proceed_to_next_step(session_id, new_context)

        elif state == 'order_confirm':
            # Xử lý sửa thông tin
            edit_match = re.search(r"sửa\s+(số lượng|sl|sđt|sdt|số điện thoại|địa chỉ|tên)\s*(.*)", message.lower())
            if edit_match:
                return self._handle_edit_field(session_id, context, edit_match)

            # Xác nhận đơn
            if intent == "confirm_order" or any(word in msg_lower for word in ["xác nhận", "xac nhan", "ok", "đồng ý", "dong y"]):
                return self._finalize_order(session_id, context)

            if any(k in msg_lower for k in ['sửa', 'thay', 'đổi']):
                return "Bạn muốn sửa trường nào? (số lượng, tên, sđt, địa chỉ) – ví dụ: 'sửa số lượng 2'"

            return "Vui lòng gõ 'xác nhận' để hoàn tất hoặc 'sửa <trường>' để chỉnh thông tin, 'hủy' để huỷ đơn."

        return "Có lỗi xảy ra. Vui lòng thử lại."

    def _handle_edit_field(self, session_id: str, context: dict, edit_match) -> str:
        """Xử lý chỉnh sửa thông tin đơn hàng"""
        field = edit_match.group(1)
        rest = edit_match.group(2).strip()
        
        if field in ['số lượng', 'sl'] and context.get('order_type') == 'single':
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
        
        return "Trường không hợp lệ. Bạn có thể sửa: số lượng, tên, sđt, địa chỉ"

    def _finalize_order(self, session_id: str, context: dict) -> str:
        """Hoàn tất và lưu đơn hàng"""
        try:
            if context.get('order_type') == 'multi':
                # 🔥 FIX: Tạo 1 đơn duy nhất với note chi tiết
                # Tính tổng tiền và tạo description
                items_description = []
                total_quantity = 0
                
                for item in context['order_items']:
                    items_description.append(f"{item['title']} x{item['quantity']}")
                    total_quantity += item['quantity']
                
                # Tạo 1 order với book_id đầu tiên, note chứa full info
                first_item = context['order_items'][0]
                order_data = {
                    'customer_name': context['customer_name'],
                    'phone': context['phone'],
                    'address': context['address'],
                    'book_id': first_item['book_id'],
                    'quantity': total_quantity,
                    'note': ' + '.join(items_description)  # Note: "Đắc Nhân Tâm x2 + Nhà giả kim x3"
                }
                
                order_id = self.db.create_order(order_data)
                
                # Hiển thị chi tiết các sách
                items_text = ""
                for i, item in enumerate(context['order_items'], 1):
                    subtotal = item['price'] * item['quantity']
                    items_text += f"  {i}. {item['title']} x{item['quantity']} = {subtotal:,.0f}đ\n"
                
                self.dialog_manager.clear_session(session_id)
                return (f"✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                        f"Mã đơn hàng: #{order_id}\n\n"
                        f"📦 Chi tiết:\n{items_text}"
                        f"💰 Tổng tiền: {context['total_price']:,.0f}đ\n"
                        f"👤 Người nhận: {context['customer_name']}\n"
                        f"📞 SĐT: {context['phone']}\n"
                        f"📍 Địa chỉ: {context['address']}\n\n"
                        f"Chúng tôi sẽ liên hệ với bạn để xác nhận.\n"
                        f"Cảm ơn bạn đã mua sách tại BookStore! 🎉")
            else:
                # Đơn sách đơn
                order_data = {
                    'customer_name': context['customer_name'],
                    'phone': context['phone'],
                    'address': context['address'],
                    'book_id': context['book_id'],
                    'quantity': context['quantity']
                }
                order_id = self.db.create_order(order_data)
                total = context['book_price'] * context['quantity']
                self.dialog_manager.clear_session(session_id)
                return (f"✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                        f"Mã đơn hàng: #{order_id}\n"
                        f"📚 Sách: {context['book_title']}\n"
                        f"🔢 Số lượng: {context['quantity']} cuốn\n"
                        f"💰 Tổng tiền: {total:,.0f}đ\n\n"
                        f"Chúng tôi sẽ liên hệ với bạn qua số {context['phone']} để xác nhận.\n"
                        f"Cảm ơn bạn đã mua sách tại BookStore! 🎉")
        except Exception as e:
            print(f"Error khi tạo đơn: {e}")
            return "Có lỗi khi tạo đơn hàng, vui lòng thử lại sau."

    # ---------------- Helper validation / parsing ----------------
    def _normalize_and_validate_quantity(self, quantity, max_stock: int) -> Optional[int]:
        """Chấp nhận int, chuỗi số, hoặc None. Trả về int hợp lệ hoặc None."""
        if quantity is None:
            return None
        
        if isinstance(quantity, str):
            quantity = quantity.strip()
            if quantity.isdigit():
                try:
                    q = int(quantity)
                except Exception:
                    return None
            else:
                nums = re.findall(r"\d+", quantity)
                q = int(nums[0]) if nums else None
        elif isinstance(quantity, int):
            q = quantity
        else:
            try:
                q = int(quantity)
            except Exception:
                return None

        if not isinstance(q, int) or q <= 0:
            return None
        if q > max_stock:
            return None
        return q

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
        # Lấy toàn bộ chữ số trong chuỗi
        digits = re.findall(r"\d+", phone_str)
        phone_only = ''.join(digits)
        
        # Kiểm tra độ dài hợp lệ
        if len(phone_only) not in [10, 11]:
            return None
        
        # Bắt buộc bắt đầu bằng số 0
        if not phone_only.startswith("0"):
            return None
        
        # Kiểm tra toàn số
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
                "• Đặt nhiều sách: 'Mua 2 đắc nhân tâm và 3 nhà giả kim'\n"
                "• Xem danh sách: 'Có những sách gì'")