
import json
import re
from pywinauto import Desktop

def extract_and_parse_chat_history():
    desktop = Desktop(backend='uia')
    
    try:
        history_win = desktop.window(title_re='.*聊天记录.*')
        if not history_win.exists():
            print("Chat history window not found")
            return
    except Exception as e:
        print(f"Error finding window: {e}")
        return
    
    try:
        msg_list = history_win.child_window(auto_id='chat_log_message_list', control_type='List')
        items = msg_list.children()
        
        parsed_history = []
        for item in items:
            raw_text = item.window_text()
            # Basic parsing: assumes time is at the end (e.g. 22:57)
            match = re.search(r'^(.*?)\s+(\d{2}:\d{2})$', raw_text)
            if match:
                content_with_sender = match.group(1)
                timestamp = match.group(2)
                
                # Further split content and sender if possible
                # This is heuristic based on the observed data
                if ' ' in content_with_sender:
                    parts = content_with_sender.split(' ', 1)
                    sender = parts[0]
                    message = parts[1]
                else:
                    sender = "Unknown/Self"
                    message = content_with_sender
                    
                parsed_history.append({
                    "sender": sender,
                    "message": message,
                    "timestamp": timestamp,
                    "raw": raw_text
                })
            else:
                parsed_history.append({
                    "sender": "Unknown",
                    "message": raw_text,
                    "timestamp": "",
                    "raw": raw_text
                })
            
        with open('wechat_history_final.json', 'w', encoding='utf-8') as f:
            json.dump(parsed_history, f, ensure_ascii=False, indent=2)
            
        print("Final parsed history saved to wechat_history_final.json")
        return parsed_history
        
    except Exception as e:
        print(f"Error extracting history: {e}")
        return None

if __name__ == "__main__":
    extract_and_parse_chat_history()
