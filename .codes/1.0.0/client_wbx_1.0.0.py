import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime

# 客户端配置
SERVER_PORT = 9999  # 端口固定

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python聊天系统")
        self.root.geometry("500x650")
        self.root.resizable(False, False)
        
        self.client_socket = None
        self.username = None
        self.server_host = None  # 服务器IP
        self.is_connected = False
        
        # 创建UI界面
        self.create_ui()
        
    def create_ui(self):
        """创建聊天界面"""
        # 1. 服务器地址区域（新增！）
        server_frame = tk.Frame(self.root)
        server_frame.pack(pady=10)
        
        tk.Label(server_frame, text="服务器地址：").grid(row=0, column=0, padx=5)
        self.server_entry = tk.Entry(server_frame, width=15)
        self.server_entry.grid(row=0, column=1, padx=5)
        self.server_entry.insert(0, "127.0.0.1")  # 默认值

        # 2. 登录区域
        login_frame = tk.Frame(self.root)
        login_frame.pack(pady=5)
        
        tk.Label(login_frame, text="用户名：").grid(row=0, column=0, padx=5)
        self.username_entry = tk.Entry(login_frame, width=20)
        self.username_entry.grid(row=0, column=1, padx=5)
        self.login_btn = tk.Button(login_frame, text="登录", command=self.login)
        self.login_btn.grid(row=0, column=2, padx=5)
        
        # 3. 聊天显示区域
        self.chat_display = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_display.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # 4. 消息输入区域
        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X)
        
        self.msg_entry = tk.Entry(input_frame)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.msg_entry.bind("<Return>", self.send_message)
        
        send_btn = tk.Button(input_frame, text="发送", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=5)
        
    def add_message(self, message):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, message + "\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def login(self):
        # 先获取服务器地址
        self.server_host = self.server_entry.get().strip()
        if not self.server_host:
            messagebox.showwarning("警告", "请输入服务器地址！")
            return

        self.username = self.username_entry.get().strip()
        if not self.username:
            messagebox.showwarning("警告", "请输入用户名！")
            return
        
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 使用你输入的服务器地址连接！
            self.client_socket.connect((self.server_host, SERVER_PORT))
            
            login_data = json.dumps({"username": self.username}, ensure_ascii=False)
            self.client_socket.send(login_data.encode('utf-8'))
            
            resp = self.client_socket.recv(1024).decode('utf-8')
            resp_data = json.loads(resp)
            if resp_data["type"] == "error":
                messagebox.showerror("错误", resp_data["msg"])
                self.client_socket.close()
                return
            
            self.is_connected = True
            self.login_btn.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.server_entry.config(state=tk.DISABLED)
            self.add_message(f"[{self.get_current_time()}] 成功连接服务器：{self.server_host}")
            self.add_message(f"[{self.get_current_time()}] 登录成功，开始聊天吧！")
            
            recv_thread = threading.Thread(target=self.receive_messages)
            recv_thread.daemon = True
            recv_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"连接服务器失败：{e}")
    
    def receive_messages(self):
        while self.is_connected:
            try:
                msg = self.client_socket.recv(1024).decode('utf-8')
                if not msg:
                    break
                
                msg_data = json.loads(msg)
                if msg_data["type"] == "message":
                    self.add_message(f"[{msg_data['time']}] {msg_data['sender']}：{msg_data['content']}")
            except:
                break
        
        self.is_connected = False
        self.add_message(f"[{self.get_current_time()}] 与服务器断开连接！")
        self.login_btn.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        self.server_entry.config(state=tk.NORMAL)
    
    def send_message(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录！")
            return
        
        msg_content = self.msg_entry.get().strip()
        if not msg_content:
            return
        
        try:
            msg_data = json.dumps({
                "type": "message",
                "content": msg_content
            }, ensure_ascii=False)
            self.client_socket.send(msg_data.encode('utf-8'))
            
            self.msg_entry.delete(0, tk.END)
            self.add_message(f"[{self.get_current_time()}] 我：{msg_content}")
        except Exception as e:
            messagebox.showerror("错误", f"发送消息失败：{e}")
    
    def get_current_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
