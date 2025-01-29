import tkinter as tk
from tkinter import ttk
import requests
import threading
import random
import time
from datetime import datetime
import queue
import urllib.parse

class BandwidthMaximizer:
    def __init__(self, root):
        self.root = root
        self.root.title("頻寬最大化工具")
        self.root.geometry("400x600")
        
        # 狀態變量
        self.is_running = False
        self.threads = []
        self.log_queue = queue.Queue()
        self.total_downloaded = 0
        self.last_check_time = time.time()
        self.last_total = 0
        
        # 創建連接池管理器
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = False
        
        # 設置連接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,    # 增加連接池大小
            pool_maxsize=20,       # 增加最大連接數
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # 添加頻寬監控變量
        self.max_speed = 0
        self.current_speed = 0
        self.speed_history = []  # 保存最近的速度記錄
        
        # 添加最高頻寬記錄
        self.max_mbps = 0
        self.max_mbps_time = None
        
        # 修改 QoS 相關變量
        self.qos_triggered = False
        self.last_qos_time = 0
        self.qos_trigger_speed = 250     # QoS 觸發閾值（Mbps）
        self.qos_wait_time = 120        # 改為 2 分鐘 (120 秒)
        self.qos_check_interval = 30    # 每 30 秒檢查一次
        self.qos_count = 0
        
        self.setup_ui()
        self.update_log()
        self.update_speed()

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 連接數設置
        ttk.Label(main_frame, text="並行連接數:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.connections_var = tk.StringVar(value="12")
        self.connections_spinbox = ttk.Spinbox(
            main_frame, 
            from_=1, 
            to=20,  # 最大 20 個連接
            textvariable=self.connections_var,
            width=10
        )
        self.connections_spinbox.grid(row=0, column=1, sticky=tk.W, pady=5)

        # 開始/停止按鈕
        self.start_button = ttk.Button(
            main_frame, 
            text="開始", 
            command=self.toggle_download
        )
        self.start_button.grid(row=1, column=0, columnspan=2, pady=10)

        # 狀態顯示
        self.status_label = ttk.Label(main_frame, text="狀態: 已停止")
        self.status_label.grid(row=2, column=0, columnspan=2, pady=5)

        # 添加最大速度顯示
        self.max_speed_label = ttk.Label(main_frame, text="最大速度: 0 MB/s")
        self.max_speed_label.grid(row=3, column=0, columnspan=2, pady=5)
        
        # 添加最高頻寬顯示（放在最大速度顯示後面）
        self.max_mbps_label = ttk.Label(main_frame, text="最高頻寬: 0 Mbps")
        self.max_mbps_label.grid(row=4, column=0, columnspan=2, pady=5)
        
        # 當前速度顯示
        self.speed_label = ttk.Label(main_frame, text="下載速度: 0 MB/s")
        self.speed_label.grid(row=5, column=0, columnspan=2, pady=5)
        
        # 添加平均速度顯示
        self.avg_speed_label = ttk.Label(main_frame, text="平均速度: 0 MB/s")
        self.avg_speed_label.grid(row=6, column=0, columnspan=2, pady=5)

        # 總計下載顯示
        self.total_label = ttk.Label(main_frame, text="總計下載: 0 MB")
        self.total_label.grid(row=7, column=0, columnspan=2, pady=5)

        # 日誌顯示
        ttk.Label(main_frame, text="運行日誌:").grid(row=8, column=0, sticky=tk.W, pady=5)
        self.log_text = tk.Text(main_frame, height=15, width=40)
        self.log_text.grid(row=9, column=0, columnspan=2, pady=5)
        
        # 滾動條
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=9, column=2, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def download_chunk(self):
        urls = [
            "http://http.speed.hinet.net/test_60m.zip",
            "http://http.speed.hinet.net/test_100m.zip",
            "http://http.speed.hinet.net/test_200m.zip"
        ]
        
        DOWNLOAD_INTERVAL = 0.2
        CHUNK_SIZE = 128 * 1024
        TIMEOUT = 10
        MAX_DOWNLOAD_TIME = 30
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Connection': 'close',   # 不保持連接
            'Host': 'http.speed.hinet.net',
            'Referer': 'https://speed.hinet.net/'
        }
        
        self.session.headers.update(headers)
        
        while self.is_running:
            # 檢查是否需要等待 QoS 冷卻
            current_time = time.time()
            if self.qos_triggered:
                wait_time = self.qos_wait_time - (current_time - self.last_qos_time)
                if wait_time > 0:
                    minutes = int(wait_time // 60)
                    seconds = int(wait_time % 60)
                    self.log_queue.put(f"QoS 冷卻中: 剩餘 {minutes}分{seconds}秒")
                    time.sleep(min(self.qos_check_interval, wait_time))  # 每 30 秒檢查一次
                    continue
                else:
                    self.qos_triggered = False
                    self.log_queue.put("QoS 冷卻完成，恢復下載")
                    self.log_queue.put("建議使用較少連接數重新開始")
            
            url = random.choice(urls)
            start_time = time.time()
            
            try:
                response = self.session.get(
                    url,
                    stream=True,
                    timeout=TIMEOUT,
                    headers=headers
                )
                
                if response.status_code == 200:
                    self.log_queue.put(f"開始下載: {url}")
                    try:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if not self.is_running:
                                return
                                
                            # 檢查下載時間
                            if time.time() - start_time > MAX_DOWNLOAD_TIME:
                                self.log_queue.put("達到最大下載時間，切換下載")
                                break
                                
                            if chunk:
                                self.total_downloaded += len(chunk)
                                
                    except Exception as e:
                        self.log_queue.put(f"下載中斷: {str(e)}")
                else:
                    self.log_queue.put(f"服務器返回: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                self.log_queue.put(f"請求錯誤: {str(e)}")
            finally:
                try:
                    response.close()
                except:
                    pass
                
            if self.is_running:
                time.sleep(DOWNLOAD_INTERVAL)

    def update_speed(self):
        if self.is_running:
            current_time = time.time()
            time_diff = current_time - self.last_check_time
            bytes_diff = self.total_downloaded - self.last_total
            
            if time_diff > 0:
                self.current_speed = bytes_diff / time_diff / (1024*1024)  # MB/s
                current_mbps = self.current_speed * 8  # 轉換為 Mbps
                
                # 檢查是否觸發 QoS
                if current_mbps > self.qos_trigger_speed:
                    self.qos_count += 1
                    if self.qos_count >= 5:  # 連續 5 次超過閾值
                        self.qos_triggered = True
                        self.last_qos_time = current_time
                        self.qos_count = 0
                        wait_minutes = self.qos_wait_time / 60
                        self.log_queue.put(f"檢測到 QoS，暫停 {wait_minutes:.1f} 分鐘")
                else:
                    self.qos_count = max(0, self.qos_count - 1)  # 逐漸減少計數
                
                # 更新最大速度
                if self.current_speed > self.max_speed:
                    self.max_speed = self.current_speed
                    self.log_queue.put(f"新的最大速度: {self.max_speed:.2f} MB/s")
                    
                    # 更新最高頻寬
                    if current_mbps > self.max_mbps:
                        self.max_mbps = current_mbps
                        self.max_mbps_time = datetime.now().strftime("%H:%M:%S")
                        self.log_queue.put(f"新的最高頻寬: {self.max_mbps:.1f} Mbps")
                        self.max_mbps_label.configure(text=f"最高頻寬: {self.max_mbps:.1f} Mbps ({self.max_mbps_time})")
                
                # 保存速度歷史
                self.speed_history.append(self.current_speed)
                if len(self.speed_history) > 10:  # 保留最近10次的記錄
                    self.speed_history.pop(0)
                
                # 計算平均速度
                avg_speed = sum(self.speed_history) / len(self.speed_history)
                
                # 更新顯示
                self.speed_label.configure(text=f"當前速度: {self.current_speed:.2f} MB/s")
                self.max_speed_label.configure(text=f"最大速度: {self.max_speed:.2f} MB/s")
                self.avg_speed_label.configure(text=f"平均速度: {avg_speed:.2f} MB/s")
                self.total_label.configure(text=f"總計下載: {self.total_downloaded/(1024*1024):.2f} MB")
                
                # 顯示當前頻寬使用率
                self.log_queue.put(f"當前頻寬使用率: {current_mbps:.1f} Mbps")
            
            self.last_check_time = current_time
            self.last_total = self.total_downloaded
        
        self.root.after(1000, self.update_speed)

    def toggle_download(self):
        if not self.is_running:
            # 開始下載
            self.is_running = True
            self.start_button.configure(text="停止")
            self.status_label.configure(text="狀態: 運行中")
            self.total_downloaded = 0
            self.last_check_time = time.time()
            self.last_total = 0
            
            # 創建下載線程
            num_connections = int(self.connections_var.get())
            self.threads = []
            for _ in range(num_connections):
                thread = threading.Thread(target=self.download_chunk)
                thread.daemon = True
                thread.start()
                self.threads.append(thread)
            
            self.log_queue.put(f"開始運行 - 使用 {num_connections} 個連接")
            self.max_speed = 0  # 重置最大速度
            self.speed_history.clear()  # 清空速度歷史
            self.max_mbps = 0  # 重置最高頻寬
            self.max_mbps_time = None
            self.qos_triggered = False
            self.qos_count = 0
        else:
            # 停止下載
            self.is_running = False
            self.start_button.configure(text="開始")
            self.status_label.configure(text="狀態: 已停止")
            self.speed_label.configure(text="下載速度: 0 MB/s")
            self.log_queue.put("停止運行")
            
            # 清理連接
            try:
                self.session.close()
            except:
                pass
            
            # 創建新的 session
            self.session = requests.Session()
            self.session.verify = False
            self.session.trust_env = False
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,    # 增加連接池大小
                pool_maxsize=20,       # 增加最大連接數
                max_retries=3,
                pool_block=False
            )
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
            
            if self.max_mbps > 0:
                self.log_queue.put(f"本次測試最高頻寬: {self.max_mbps:.1f} Mbps (達到時間: {self.max_mbps_time})")

    def update_log(self):
        while not self.log_queue.empty():
            message = self.log_queue.get()
            current_time = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{current_time}] {message}\n")
            self.log_text.see(tk.END)
        
        self.root.after(100, self.update_log)

if __name__ == "__main__":
    root = tk.Tk()
    app = BandwidthMaximizer(root)
    root.mainloop() 