import requests
import json
import os
from PIL import Image

CACHE_FILE = 'ocr_cache.json'

def get_image_hash(image_path, hash_size=8):
    """ 计算图片的感知哈希 (dHash) 作为缓存 key """
    try:
        with Image.open(image_path) as img:
            # 1. 缩小图片并转为灰度
            img = img.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            # 2. 计算每一行相邻像素差异
            difference = []
            for row in range(hash_size):
                for col in range(hash_size):
                    pixel_left = pixels[row * (hash_size + 1) + col]
                    pixel_right = pixels[row * (hash_size + 1) + col + 1]
                    difference.append(pixel_left > pixel_right)
            # 3. 将二进制转为十六进制字符串
            decimal_value = 0
            hex_string = []
            for i, bit in enumerate(difference):
                if bit:
                    decimal_value += 2**(i % 8)
                if (i % 8) == 7:
                    hex_string.append(hex(decimal_value)[2:].rjust(2, '0'))
                    decimal_value = 0
            return "".join(hex_string)
    except Exception as e:
        print(f"Error computing hash: {e}")
        return None

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

def ocr_space_file(filename, overlay=False, api_key='helloworld', language='eng'):
    """ OCR.space API 请求 """
    payload = {'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               }
    with open(filename, 'rb') as f:
        r = requests.post('https://api.ocr.space/parse/image',
                          files={filename: f},
                          data=payload,
                          )
    return r.content.decode()

def main():
    file_path = ''
    api_key = ''
    
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    # 1. 计算图片哈希
    img_hash = get_image_hash(file_path)
    if not img_hash:
        print("Failed to hash image.")
        return
    
    # 2. 检查缓存
    cache = load_cache()
    if img_hash in cache:
        print(f"Cache Hit! (Hash: {img_hash})")
        print("\n--- Parsed Text (From Cache) ---")
        print(cache[img_hash])
        return

    # 3. 缓存未命中，调用 OCR
    print(f"Cache Miss (Hash: {img_hash}), calling OCR.space API...")
    try:
        result_json = ocr_space_file(filename=file_path, api_key=api_key)
        result = json.loads(result_json)
        
        if result.get('OCRExitCode') == 1:
            parsed_text = ""
            for res in result.get('ParsedResults', []):
                parsed_text += res.get('ParsedText') + "\n"
            
            # 4. 保存到缓存
            cache[img_hash] = parsed_text.strip()
            save_cache(cache)
            
            print("\n--- Parsed Text (New Result) ---")
            print(cache[img_hash])
        else:
            print(f"OCR failed: {result.get('ErrorMessage') or result.get('ErrorDetails')}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
