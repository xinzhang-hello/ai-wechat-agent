#!/usr/bin/env python3
import sys
import time
import argparse
from wechat_utils import get_main_window, open_chat, send_message, get_last_messages

def ai_chat_loop(win, name, interval=2):
    """
    Auto-response loop:
    1. Poll for the latest message.
    2. If the latest message is from the other side ('left'), reply with 'Text +AI'.
    3. Wait for the next message.
    """
    print(f"Starting AI Chat with '{name}'...")
    print("Press Ctrl+C to stop.")
    
    # Track the last message we've seen to avoid double-responding
    last_seen_msg_text = None
    
    # Initialize: find the last message currently in the chat
    initial_msgs = get_last_messages(win, count=1)
    if initial_msgs and initial_msgs[-1]['side'] == 'left':
        last_seen_msg_text = initial_msgs[-1]['text']
        print(f"Initial last message from {name}: '{last_seen_msg_text}'")

    try:
        while True:
            msgs = get_last_messages(win, count=1)
            if not msgs:
                time.sleep(interval)
                continue
            
            latest = msgs[-1]
            
            # If the latest message is from the other side and it's new
            if latest['type'] == 'message' and latest['side'] == 'left':
                current_text = latest['text']
                
                if current_text != last_seen_msg_text:
                    print(f"\n[Received from {name}]: {current_text}")
                    
                    # Construct response
                    response_text = f"{current_text} +AI"
                    print(f"[AI Response]: {response_text}")
                    
                    # Send response
                    if send_message(win, response_text):
                        # Update last_seen to the message WE just sent to avoid 
                        # re-processing the same incoming message
                        last_seen_msg_text = current_text
                    else:
                        print("Failed to send AI response.")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nAI Chat stopped by user.")

def main():
    parser = argparse.ArgumentParser(description='WeChat AI Auto-Responder')
    parser.add_argument('name', help='Contact name to chat with')
    parser.add_argument('--interval', type=int, default=2, help='Polling interval in seconds')
    args = parser.parse_args()

    win = get_main_window()
    if not win:
        print("WeChat not found. Please ensure WeChat is running and logged in.")
        return

    print(f"Connecting to chat with '{args.name}'...")
    if open_chat(win, args.name):
        ai_chat_loop(win, args.name, interval=args.interval)
    else:
        print(f"Could not open chat with '{args.name}'. Check the name and try again.")

if __name__ == '__main__':
    main()
