#!/usr/bin/env python3
import sys
import time
import argparse
from wechat_utils import get_main_window, open_chat, send_message, get_history_messages, init_db, log_message

def group_chat_loop(win, chat_name, interval=2):
    """
    Enhanced AI Chat Loop for Groups:
    - Identifies different senders.
    - Logs ALL messages (sent/received) to SQLite.
    - Auto-responds to others' messages.
    """
    print(f"Starting Group AI Chat in '{chat_name}'...")
    db_conn = init_db()
    
    # Track state to avoid double logging or responding
    # Initialize with CURRENT history to ignore existing messages
    print("Initializing chat state (ignoring history)...")
    initial_msgs = get_history_messages(win, count=10)
    last_processed_msgs = [(m['sender'], m['text']) for m in initial_msgs]
    print(f"Skipped {len(last_processed_msgs)} historical messages.")

    try:
        while True:
            # Get last 5 messages to ensure we don't miss any due to timing
            current_msgs = get_history_messages(win, count=5)
            
            for msg in current_msgs:
                msg_id = (msg['sender'], msg['text'])
                
                if msg_id not in last_processed_msgs:
                    # New message detected!
                    sender = msg['sender']
                    text = msg['text']
                    side = msg.get('side', 'unknown')
                    
                    print(f"[{sender}]: {text}")
                    
                    # 1. Log to SQLite
                    log_message(db_conn, chat_name, sender, text, side)
                    
                    # 2. Auto-respond if it's from someone else
                    if side == 'left':
                        response_text = f"{text} +AI"
                        print(f"  -> AI Response: {response_text}")
                        if send_message(win, response_text):
                            # After sending, we should log OUR response too
                            # But our response will be captured in the next poll as 'Self'
                            pass
                    
                    # Keep track of processed messages
                    last_processed_msgs.append(msg_id)
                    if len(last_processed_msgs) > 20:
                        last_processed_msgs.pop(0)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nGroup AI Chat stopped.")
    finally:
        db_conn.close()

def main():
    parser = argparse.ArgumentParser(description='WeChat Group AI Auto-Responder & Logger')
    parser.add_argument('name', help='Chat/Group name to join')
    parser.add_argument('--interval', type=float, default=2.0, help='Polling interval')
    args = parser.parse_args()

    win = get_main_window()
    if not win:
        print("WeChat not found.")
        return

    print(f"Opening chat '{args.name}'...")
    if open_chat(win, args.name):
        group_chat_loop(win, args.name, interval=args.interval)
    else:
        print(f"Failed to open chat '{args.name}'.")

if __name__ == '__main__':
    main()
