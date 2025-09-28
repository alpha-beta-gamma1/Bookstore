import json
import os
from typing import Dict, Optional
from datetime import datetime

class DialogManager:
    def __init__(self):
        self.sessions_dir = 'data/sessions'
        os.makedirs(self.sessions_dir, exist_ok=True)
        self.sessions = {}
    
    def get_session(self, session_id: str) -> Dict:
        """Lấy thông tin phiên làm việc"""
        if session_id not in self.sessions:
            session_file = os.path.join(self.sessions_dir, f'{session_id}.json')
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    self.sessions[session_id] = json.load(f)
            else:
                self.sessions[session_id] = {
                    'id': session_id,
                    'state': 'idle',
                    'context': {},
                    'created_at': datetime.now().isoformat()
                }
        
        return self.sessions[session_id]
    
    def update_session(self, session_id: str, state: str = None, context: Dict = None):
        """Cập nhật thông tin phiên"""
        session = self.get_session(session_id)
        
        if state:
            session['state'] = state
        
        if context is not None:
            # FIX: Thay thế hoàn toàn context thay vì merge
            session['context'].update(context)
        
        session['updated_at'] = datetime.now().isoformat()
        
        # Debug log
        print(f"DEBUG DialogManager.update_session:")
        print(f"  - session_id: {session_id}")
        print(f"  - new state: {state}")
        print(f"  - new context: {context}")
        print(f"  - updated session context: {session['context']}")
        
        # Lưu vào file
        session_file = os.path.join(self.sessions_dir, f'{session_id}.json')
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
    
    def clear_session(self, session_id: str):
        """Xóa phiên làm việc"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        session_file = os.path.join(self.sessions_dir, f'{session_id}.json')
        if os.path.exists(session_file):
            os.remove(session_file)
        
        # Tạo session mới với state idle
        self.sessions[session_id] = {
            'id': session_id,
            'state': 'idle',
            'context': {},
            'created_at': datetime.now().isoformat()
        }
    
    def get_state(self, session_id: str) -> str:
        """Lấy trạng thái hiện tại của phiên"""
        session = self.get_session(session_id)
        return session.get('state', 'idle')
    
    def get_context(self, session_id: str) -> Dict:
        """Lấy ngữ cảnh của phiên"""
        session = self.get_session(session_id)
        return session.get('context', {})
        
    def debug_session(self, session_id: str):
        """Debug session info"""
        session = self.get_session(session_id)
        print(f"=== SESSION DEBUG ===")
        print(f"Session ID: {session_id}")
        print(f"State: {session.get('state')}")
        print(f"Context: {session.get('context')}")
        print(f"In memory: {session_id in self.sessions}")
        
        session_file = os.path.join(self.sessions_dir, f'{session_id}.json')
        print(f"File exists: {os.path.exists(session_file)}")
        if os.path.exists(session_file):
            with open(session_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
            print(f"File content: {file_data}")
        print(f"====================")