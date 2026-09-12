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

        # 4. 消息输入区域
        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X, side=tk.BOTTOM)

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

        self.msg_text = tk.Text(input_frame, height=4, font=("Consolas", 9))
        self.msg_text.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 5))

        self.msg_text.bind("<Return>", self.handle_enter)
        self.msg_text.bind("<Shift-Return>", self.handle_shift_enter)

    def show_emoji_popup(self):
        # 全兼容 Windows 经典表情，无任何显示异常字符
        emojis = [
            "😊", "😂", "😃", "😄", "😅", "😆", "😉", "😇",
            "😍", "🤩", "😘", "😗", "😙", "😚", "🙂", "🤗",
            "🤔", "😐", "😑", "🙄", "😏", "😜", "😝", "😛",
            "🥳", "😎", "🥺", "😢", "😭", "😤", "😠", "😡",
            "😔", "😟", "😕", "🙁", "😮", "😯", "😲", "😳",
            "👍", "👎", "✊", "✌️", "🤞", "🤝", "🙏", "👏",
            "🙌", "👌", "✋", "👋", "🤙", "💪", "👀", "🔥",
            "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "💔",
            "💕", "💞", "💓", "💗", "💖", "💘", "💝", "💟",
            "🎉", "🎊", "🎂", "🎁", "🎀", "🏆", "🎵", "🎶",
            "⭐", "🌟", "✨", "💫", "🌙", "☀️", "🌈", "🌊",
            "🐶", "🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼",
            "🍎", "🍐", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓",
            "🌹", "🌷", "🌺", "🌸", "🌼", "💐", "🌻", "🍀",
            "🚗", "🚲", "✈️", "🚀", "📱", "💻", "🎧", "📷",
            "🌱", "🌲", "🌳", "🌴", "🌵", "🍁", "🍂", "🌾"
        ]

        popup = tk.Toplevel(self.root)
        popup.title("表情面板")
        popup.geometry("460x300")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.geometry(f"+{self.root.winfo_x()+20}+{self.root.winfo_y()+300}")

        # 带滚动条 + 鼠标滚轮
        canvas = tk.Canvas(popup, highlightthickness=0)
        scrollbar = tk.Scrollbar(popup, orient=tk.VERTICAL, command=canvas.yview)
        frame = tk.Frame(canvas)

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮支持
        def on_wheel(e):
            canvas.yview_scroll(-int(e.delta / 120), "units")

        canvas.bind("<MouseWheel>", on_wheel)
        frame.bind("<MouseWheel>", on_wheel)
        popup.bind("<MouseWheel>", on_wheel)

        cols = 9
        for idx, em in enumerate(emojis):
            btn = tk.Button(
                frame, text=em, font=("Segoe UI Emoji", 16), width=3, height=1,
                bg="white", relief=tk.FLAT, bd=1,
                command=lambda e=em, p=popup: [self.insert_emoji(e), p.destroy()]
            )
            btn.grid(row=idx // cols, column=idx % cols, padx=2, pady=2)

    def insert_emoji(self, emoji):
        self.msg_text.insert(tk.INSERT, emoji)
        self.msg_text.focus()

    def handle_shift_enter(self, event):
        self.msg_text.insert(tk.INSERT, "\n")
        return "break"

    def handle_enter(self, event):
        self.send_message()
        return "break"

    def calc_indent_spaces(self, sender_header):
        space_count = 0
        for char in sender_header:
            if '\u4e00' <= char <= '\u9fff' or '\uff00' <= char <= '\uffef':
                space_count += 2
            else:
                space_count += 1
        return space_count

    def add_message(self, message):
        self.msg_queue.put(message)

    def process_msg_queue(self):
        try:
            while True:
                message = self.msg_queue.get_nowait()
                self.chat_display.config(state=tk.NORMAL)
                lines = message.split("\n")
                if len(lines) > 1:
                    base_line = lines[0]
                    if "：" in base_line:
                        sender_header = base_line.split("：")[0] + "："
                        indent = " " * self.calc_indent_spaces(sender_header)
                        new_lines = [base_line] + [indent + line for line in lines[1:]]
                        message = "\n".join(new_lines)
                self.chat_display.insert(tk.END, message + "\n")
                line_count = int(self.chat_display.index('end-1c').split('.')[0])
                if line_count > 1000:
                    self.chat_display.delete(1.0, f"{line_count - 1000}.0")
                self.chat_display.config(state=tk.DISABLED)
                self.chat_display.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self.process_msg_queue)

    def save_chat_records(self):
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
        if messagebox.askyesno("确认", "确定要清空聊天记录吗？"):
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.add_message(f"[{self.get_current_time()}] 聊天记录已清空")

    def login(self):
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
            self.client_socket.settimeout(10)
            self.client_socket.connect((self.server_host, SERVER_PORT))

            login_data = json.dumps({"username": self.username}, ensure_ascii=False)
            self.client_socket.send(login_data.encode('utf-8'))

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
        msg_buffer = ""
        while self.is_connected:
            try:
                chunk = self.client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                msg_buffer += chunk

                while msg_buffer:
                    try:
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
                        continue

            except socket.timeout:
                continue
            except Exception as e:
                self.add_message(f"[{self.get_current_time()}] 接收消息异常：{str(e)}")
                break

        self.is_connected = False
        self.add_message(f"[{self.get_current_time()}] 与服务器断开连接！")
        self.login_btn.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        self.server_entry.config(state=tk.NORMAL)

    def send_message(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录服务器！")
            return

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

            if len(msg_data.encode('utf-8')) > 1024:
                for i in range(0, len(msg_data), 1024):
                    self.client_socket.send(msg_data[i:i+1024].encode('utf-8'))
            else:
                self.client_socket.send(msg_data.encode('utf-8'))

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
