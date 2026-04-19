import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox
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
        self.server_host = None
        self.is_connected = False
        
        self.create_ui()
        
    def create_ui(self):
        """创建聊天界面（包含发送按钮）"""
        # 1. 服务器地址区域
        server_frame = tk.Frame(self.root)
        server_frame.pack(pady=10)
        
        tk.Label(server_frame, text="服务器地址：").grid(row=0, column=0, padx=5)
        self.server_entry = tk.Entry(server_frame, width=15)
        self.server_entry.grid(row=0, column=1, padx=5)
        self.server_entry.insert(0, "127.0.0.1")

        # 2. 登录区域
        login_frame = tk.Frame(self.root)
        login_frame.pack(pady=5)
        
        tk.Label(login_frame, text="用户名：").grid(row=0, column=0, padx=5)
        self.username_entry = tk.Entry(login_frame, width=20)
        self.username_entry.grid(row=0, column=1, padx=5)
        self.login_btn = tk.Button(login_frame, text="登录", command=self.login)
        self.login_btn.grid(row=0, column=2, padx=5)
        
        # 3. 聊天显示区域（等宽字体）
        self.chat_display = scrolledtext.ScrolledText(
            self.root, 
            wrap=tk.WORD, 
            state=tk.DISABLED,
            font=("Consolas", 9)
        )
        self.chat_display.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # 4. 消息输入区域（核心：输入框+发送按钮）
        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X)
        
        # 多行输入框（靠左，占满剩余空间）
        self.msg_text = tk.Text(input_frame, height=4, font=("Consolas", 9))
        self.msg_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))  # 右侧留5px间距
        
        # 发送按钮（靠右，和输入框垂直对齐）
        self.send_btn = tk.Button(
            input_frame, 
            text="发送", 
            command=self.send_message,  # 绑定发送方法
            width=8,  # 固定按钮宽度，更美观
            height=4   # 高度和输入框匹配
        )
        self.send_btn.pack(side=tk.RIGHT)
        
        # 按键绑定：Shift+Enter换行，Enter发送
        self.msg_text.bind("<Return>", self.handle_enter)
        self.msg_text.bind("<Shift-Return>", self.handle_shift_enter)
        
    def handle_shift_enter(self, event):
        """Shift+Enter：换行"""
        self.msg_text.insert(tk.INSERT, "\n")
        return "break"
    
    def handle_enter(self, event):
        """Enter：发送消息"""
        self.send_message()
        return "break"
    
    def calc_indent_spaces(self, sender_header):
        """计算缩进空格数（中文=2个空格，英文=1个）"""
        space_count = 0
        for char in sender_header:
            if '\u4e00' <= char <= '\u9fff' or '\uff00' <= char <= '\uffef':
                space_count += 2
            else:
                space_count += 1
        return space_count
        
    def add_message(self, message):
        """添加消息到显示区，保持对齐"""
        self.chat_display.config(state=tk.NORMAL)
        lines = message.split("\n")
        if len(lines) > 1:
            base_line = lines[0]
            if "：" in base_line:
                sender_header = base_line.split("：")[0] + "："
                indent_spaces = self.calc_indent_spaces(sender_header)
                indent = " " * indent_spaces
                new_lines = [base_line] + [indent + line for line in lines[1:]]
                message = "\n".join(new_lines)
        self.chat_display.insert(tk.END, message + "\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def login(self):
        """登录逻辑（无修改）"""
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
        """接收消息逻辑（无修改）"""
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
        """发送消息逻辑（按钮和Enter键共用）"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录！")
            return
        
        # 读取输入框内容（去掉首尾空白）
        msg_content = self.msg_text.get("1.0", tk.END).strip()
        if not msg_content:
            return
        
        try:
            msg_data = json.dumps({
                "type": "message",
                "content": msg_content
            }, ensure_ascii=False)
            self.client_socket.send(msg_data.encode('utf-8'))
            
            # 清空输入框
            self.msg_text.delete("1.0", tk.END)
            self.add_message(f"[{self.get_current_time()}] 我：{msg_content}")
        except Exception as e:
            messagebox.showerror("错误", f"发送消息失败：{e}")
    
    def get_current_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
