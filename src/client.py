import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from datetime import datetime
import queue

# 客户端配置
SERVER_PORT = 9999  # 端口固定

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python聊天系统")
        self.root.geometry("500x700")
        self.root.resizable(False, False)
        
        self.client_socket = None
        self.username = None
        self.server_host = None
        self.is_connected = False
        self.msg_queue = queue.Queue()  # 消息队列，防止UI阻塞
        
        self.create_ui()
        
        # 启动消息处理循环
        self.process_msg_queue()
    
    def create_ui(self):
        """创建聊天界面（完全保留原版UI，仅新增Emoji按钮）"""
        # 1. 服务器地址区域
        server_frame = tk.Frame(self.root)
        server_frame.pack(pady=10, padx=10, fill=tk.X)
        
        tk.Label(server_frame, text="服务器地址：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.server_entry = tk.Entry(server_frame, width=15)
        self.server_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        self.server_entry.insert(0, "127.0.0.1")
        # 2. 登录区域
        login_frame = tk.Frame(self.root)
        login_frame.pack(pady=5, padx=10, fill=tk.X)
        
        tk.Label(login_frame, text="用户名：").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.username_entry = tk.Entry(login_frame, width=20)
        self.username_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        self.login_btn = tk.Button(login_frame, text="登录", command=self.login, width=8)
        self.login_btn.grid(row=0, column=2, padx=5, sticky=tk.W)
        
        # 聊天记录操作按钮区域
        chat_op_frame = tk.Frame(self.root)
        chat_op_frame.pack(pady=5, padx=10, fill=tk.X)
        tk.Button(chat_op_frame, text="保存聊天记录", bg='#27ae60', fg='white', 
                  command=self.save_chat_records, width=12).pack(side=tk.LEFT, padx=2)
        tk.Button(chat_op_frame, text="清空聊天记录", bg='#e74c3c', fg='white', 
                  command=self.clear_chat_records, width=12).pack(side=tk.LEFT, padx=2)
        
        # 3. 聊天显示区域（等宽字体，原版样式）
        self.chat_display = scrolledtext.ScrolledText(
            self.root, 
            wrap=tk.WORD, 
            state=tk.DISABLED,
            font=("Consolas", 9)
        )
        self.chat_display.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # 4. 消息输入区域（完全保留原版布局，仅在发送按钮左侧加Emoji按钮）
        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X, side=tk.BOTTOM)
        
        # 发送按钮（原版样式，位置不变）
        self.send_btn = tk.Button(
            input_frame, 
            text="发送", 
            command=self.send_message,
            width=8,          
            height=4,
            bg="#4CAF50",     
            fg="white"        
        )
        self.send_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # ===== 仅新增：Emoji表情按钮（和原版UI风格一致，无视觉改动）=====
        self.emoji_btn = tk.Button(
            input_frame,
            text="😊",
            width=3,
            height=4,
            bg="#f0f0f0",
            fg="#333333",
            command=self.show_emoji_popup
        )
        self.emoji_btn.pack(side=tk.RIGHT, padx=(0, 5))
        # ==============================================================
        
        # 多行输入框（原版位置/样式，无任何改动）
        self.msg_text = tk.Text(input_frame, height=4, font=("Consolas", 9))
        self.msg_text.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 按键绑定：原版Shift+Enter换行，Enter发送，无改动
        self.msg_text.bind("<Return>", self.handle_enter)
        self.msg_text.bind("<Shift-Return>", self.handle_shift_enter)
    
    # ===== 升级：超大表情面板 + 海量Emoji =====
    def show_emoji_popup(self):
        """弹出超大Emoji选择窗口，海量表情可选"""
        # 扩充至96个常用Emoji，分类更丰富
        emojis = [
            # 笑脸情绪
            "😊", "😂", "🤣", "😃", "😄", "😅", "😆", "😉",
            "😇", "😍", "🤩", "😘", "😗", "😙", "😚", "🙂",
            # 搞怪表情
            "🤔", "🤨", "😐", "😑", "😶", "🙄", "😏", "😜",
            "😝", "😛", "🤪", "🤩", "🥳", "😎", "🤓", "🥺",
            # 负面情绪
            "😢", "😭", "😤", "😠", "😡", "🤬", "😔", "😟",
            "😕", "🙁", "☹️", "😮", "😯", "😲", "😳", "🥴",
            # 手势动作
            "👍", "👎", "✊", "✌️", "🤞", "🤝", "🙏", "👏",
            "🙌", "🤲", "🤚", "🖐️", "🖖", "👌", "🤏", "✋",
            # 爱心情感
            "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "💔",
            "💕", "💞", "💓", "💗", "💖", "💘", "💝", "💟",
            # 节日物品
            "🎉", "🎊", "🎈", "🎂", "🎁", "🎀", "🏆", "🎵",
            "🎶", "🔥", "💯", "⭐", "🌟", "✨", "💫", "🌙"
        ]
        popup = tk.Toplevel(self.root)
        popup.title("表情面板")
        # 扩大窗口尺寸：480x320，更大更舒适
        popup.geometry("480x320")
        popup.resizable(False, False)
        popup.transient(self.root)
        # 优化弹窗位置
        popup.geometry(f"+{self.root.winfo_x()+10}+{self.root.winfo_y()+300}")
        
        # 滚动框架 + 表情容器
        canvas = tk.Canvas(popup)
        scrollbar = tk.Scrollbar(popup, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        scrollbar.pack(side="right", fill="y")

        # 12列布局，自动换行
        cols = 12
        for idx, emoji in enumerate(emojis):
            btn = tk.Button(
                scrollable_frame,
                text=emoji,
                font=("Segoe UI Emoji", 16),
                width=3,
                height=1,
                bg="white",
                relief=tk.FLAT,
                bd=1,
                command=lambda e=emoji, p=popup: [self.insert_emoji(e), p.destroy()]
            )
            btn.grid(row=idx//cols, column=idx%cols, padx=3, pady=3)
    
    def insert_emoji(self, emoji):
        """将选中的Emoji插入输入框，保持光标位置"""
        self.msg_text.insert(tk.INSERT, emoji)
        self.msg_text.focus()
    # ==============================================================
    
    # 以下所有方法：完全保留原版逻辑，无任何修改
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
        """线程安全添加消息到显示区，防止大量消息导致UI阻塞"""
        self.msg_queue.put(message)
    
    def process_msg_queue(self):
        """处理消息队列，更新UI（主线程执行）"""
        try:
            while True:
                message = self.msg_queue.get_nowait()
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
                # 限制聊天记录长度，防止内存溢出（保留最新1000行）
                line_count = int(self.chat_display.index('end-1c').split('.')[0])
                if line_count > 1000:
                    self.chat_display.delete(1.0, f"{line_count - 1000}.0")
                self.chat_display.config(state=tk.DISABLED)
                self.chat_display.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self.process_msg_queue)  # 50ms检查一次队列
    
    def save_chat_records(self):
        """保存聊天记录到文件"""
        chat_content = self.chat_display.get(1.0, tk.END)
        if not chat_content.strip():
            messagebox.showinfo("提示", "聊天记录为空，无需保存")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="保存聊天记录"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(chat_content)
                messagebox.showinfo("成功", f"聊天记录已保存到：{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存聊天记录失败：{e}")
    
    def clear_chat_records(self):
        """清空聊天记录"""
        if messagebox.askyesno("确认", "确定要清空聊天记录吗？"):
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.add_message(f"[{self.get_current_time()}] 聊天记录已清空")
    
    def login(self):
        """登录逻辑"""
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
            # 设置套接字超时，防止连接阻塞
            self.client_socket.settimeout(10)
            self.client_socket.connect((self.server_host, SERVER_PORT))
            
            login_data = json.dumps({"username": self.username}, ensure_ascii=False)
            self.client_socket.send(login_data.encode('utf-8'))
            
            # 原版无服务端返回校验，直接判定登录成功（和原版一致）
            self.is_connected = True
            self.login_btn.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.server_entry.config(state=tk.DISABLED)
            self.add_message(f"[{self.get_current_time()}] 成功连接服务器：{self.server_host}")
            self.add_message(f"[{self.get_current_time()}] 登录成功，开始聊天吧！")
            
            # 启动接收线程（守护线程）
            recv_thread = threading.Thread(target=self.receive_messages)
            recv_thread.daemon = True
            recv_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"连接服务器失败：{e}")
    
    def receive_messages(self):
        """优化接收消息逻辑，防止大量消息导致闪退"""
        msg_buffer = ""  # 消息缓冲区，处理粘包
        while self.is_connected:
            try:
                # 增大接收缓冲区，分段接收
                chunk = self.client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                msg_buffer += chunk
                
                # 按JSON边界分割消息，处理粘包
                while msg_buffer:
                    try:
                        # 查找JSON结束符
                        end_idx = msg_buffer.rfind('}') + 1
                        if end_idx <= 0:
                            break
                        msg_str = msg_buffer[:end_idx]
                        msg_buffer = msg_buffer[end_idx:]
                        
                        msg_data = json.loads(msg_str)
                        if msg_data["type"] == "message":
                            self.add_message(f"[{msg_data['time']}] {msg_data['sender']}：{msg_data['content']}")
                        elif msg_data["type"] == "system":
                            self.add_message(f"[{msg_data['time']}] 系统提示：{msg_data['content']}")
                        elif msg_data["type"] == "notice":
                            self.add_message(f"[{msg_data['time']}] 服务器公告：{msg_data['content']}")
                    except json.JSONDecodeError:
                        # 未接收完整，继续缓冲
                        continue
                    
            except socket.timeout:
                continue
            except Exception as e:
                # 捕获异常，防止线程崩溃
                self.add_message(f"[{self.get_current_time()}] 接收消息异常：{str(e)}")
                break
        
        self.is_connected = False
        self.add_message(f"[{self.get_current_time()}] 与服务器断开连接！")
        self.login_btn.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        self.server_entry.config(state=tk.NORMAL)
    
    def send_message(self, event=None):
        """发送消息逻辑（按钮和Enter键共用）"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录服务器！")
            return
        
        # 读取输入框内容（去掉首尾空白）
        msg_content = self.msg_text.get("1.0", tk.END).strip()
        if not msg_content:
            messagebox.showinfo("提示", "消息内容不能为空！")
            return
        
        try:
            msg_data = json.dumps({
                "type": "message",
                "content": msg_content,
                "sender": self.username,
                "time": self.get_current_time()
            }, ensure_ascii=False)
            # 分段发送大消息
            if len(msg_data.encode('utf-8')) > 1024:
                for i in range(0, len(msg_data), 1024):
                    chunk = msg_data[i:i+1024]
                    self.client_socket.send(chunk.encode('utf-8'))
            else:
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
