import requests
import time
import concurrent.futures
import logging
from datetime import datetime
import random

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bandwidth_usage.log'
)

def download_chunk():
    """
    持續下載數據的函數
    """
    try:
        # 使用 Cloudflare 的速度測試文件，響應更快
        urls = [
            "https://speed.cloudflare.com/100mb",
            "https://speed.cloudflare.com/500mb",
            "http://speedtest.ftp.otenet.gr/files/test100Mb.db"
        ]
        
        # 隨機選擇一個測試文件
        url = random.choice(urls)
        with requests.get(url, stream=True) as response:
            for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
                if chunk:
                    pass  # 只下載不保存
    except Exception as e:
        logging.error(f"下載出錯: {str(e)}")

def main():
    # 減少連接數可以降低佔用的頻寬
    num_connections = 1  # 改為較小的數字，如 1 或 2
    
    while True:
        try:
            logging.info("開始新的下載週期")
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_connections) as executor:
                # 創建多個並行下載任務
                futures = [executor.submit(download_chunk) for _ in range(num_connections)]
                concurrent.futures.wait(futures)
        except KeyboardInterrupt:
            logging.info("程序被用戶中止")
            break
        except Exception as e:
            logging.error(f"主程序出錯: {str(e)}")
            time.sleep(5)  # 出錯時等待5秒後重試

if __name__ == "__main__":
    main() 