import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from datetime import datetime
import queue
import os
import sys
import subprocess
import base64
import uuid

# 客户端配置
SERVER_PORT = 9999  # 端口固定
MAX_FILE_SIZE = 20 * 1024 * 1024  # 单个文件最大 20MB
CHUNK_SIZE = 3 * 1024             # 二进制分块大小（base64 后约 4KB）


def format_size(num_bytes):
    """把字节数格式化成易读字符串"""
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "未知大小"
    if num_bytes < 1024:
        return f"{int(num_bytes)} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def send_json(sock, data):
    """以「一行一条 JSON」的协议发送数据"""
    try:
        payload = (json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8')
        sock.sendall(payload)
        return True
    except Exception:
        return False


class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python聊天系统")
        self.root.geometry("520x760")
        self.root.resizable(False, False)

        self.client_socket = None
        self.username = None
        self.server_host = None
        self.is_connected = False
        self.msg_queue = queue.Queue()  # 消息队列，防止UI阻塞

        # 文件相关状态
        self.file_offers = {}      # file_id -> {'filename', 'size'}  可下载的文件
        self.file_downloads = {}   # file_id -> {'filename','total','chunks'}
        self.downloading = set()   # 正在下载中的 file_id

        self.create_ui()

        # 启动消息处理循环
        self.process_msg_queue()

    def create_ui(self):
        """创建聊天界面"""
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

        # 3. 聊天显示区域
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

        self.file_btn = tk.Button(
            input_frame,
            text="📎",
            width=3,
            height=4,
            bg="#f0f0f0",
            fg="#333333",
            command=self.choose_and_send_file
        )
        self.file_btn.pack(side=tk.RIGHT, padx=(0, 5))

        self.msg_text = tk.Text(input_frame, height=4, font=("Consolas", 9))
        self.msg_text.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 5))

        self.msg_text.bind("<Return>", self.handle_enter)
        self.msg_text.bind("<Shift-Return>", self.handle_shift_enter)

    # ---------------- 表情面板 ----------------
    def show_emoji_popup(self):
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

    # ---------------- 消息队列处理 ----------------
    def add_message(self, message):
        """普通文本消息"""
        self.msg_queue.put(('text', message))

    def add_file_message(self, time_str, sender, file_id, filename, size,
                         is_own=False, local_path=None):
        """文件消息（可点击）"""
        self.msg_queue.put(('file', {
            'time': time_str,
            'sender': sender,
            'file_id': file_id,
            'filename': filename,
            'size': size,
            'is_own': is_own,
            'local_path': local_path,
        }))

    def _append_text(self, message):
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
        self._trim_lines()
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _append_file(self, data):
        file_id = data['file_id']
        filename = data['filename']
        size = data['size']
        sender = data['sender']
        time_str = data['time']
        is_own = data['is_own']
        local_path = data.get('local_path')

        self.chat_display.config(state=tk.NORMAL)
        if is_own:
            prefix = f"[{time_str}] 我："
            suffix = "  ✅ 已发送（点击打开本地文件）"
        else:
            prefix = f"[{time_str}] {sender}："
            suffix = "  📥 点击下载"

        self.chat_display.insert(tk.END, prefix)
        tag_name = f"filelink_{file_id}"
        self.chat_display.insert(
            tk.END,
            f"📎 {filename}（{format_size(size)}）{suffix}",
            (tag_name,)
        )
        self.chat_display.insert(tk.END, "\n")

        if is_own and local_path:
            self.chat_display.tag_config(tag_name, foreground='#27ae60', underline=True)
            self.chat_display.tag_bind(
                tag_name, '<Button-1>',
                lambda e, p=local_path: self._open_local_file(p)
            )
        else:
            self.chat_display.tag_config(tag_name, foreground='#2980b9', underline=True)
            self.chat_display.tag_bind(
                tag_name, '<Button-1>',
                lambda e, fid=file_id, fn=filename: self.request_file_download(fid, fn)
            )

        self._trim_lines()
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _trim_lines(self):
        line_count = int(self.chat_display.index('end-1c').split('.')[0])
        if line_count > 1000:
            self.chat_display.delete(1.0, f"{line_count - 1000}.0")

    def process_msg_queue(self):
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == 'text':
                    self._append_text(data)
                elif kind == 'file':
                    self._append_file(data)
                elif kind == 'save_file':
                    self._ask_and_save(data['filename'], data['data'])
                elif kind == 'popup':
                    messagebox.showwarning(data.get('title', '提示'), data.get('msg', ''))
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self.process_msg_queue)

    def _ask_and_save(self, filename, raw):
        file_path = filedialog.asksaveasfilename(
            initialfile=filename,
            title=f"保存文件：{filename}"
        )
        if not file_path:
            self.add_message(f"[{self.get_current_time()}] 已取消保存：{filename}")
            return
        try:
            with open(file_path, 'wb') as f:
                f.write(raw)
            self.add_message(f"[{self.get_current_time()}] 文件已保存：{file_path}")
        except Exception as e:
            self.add_message(f"[{self.get_current_time()}] 保存失败：{e}")

    def calc_indent_spaces(self, sender_header):
        space_count = 0
        for char in sender_header:
            if '\u4e00' <= char <= '\u9fff' or '\uff00' <= char <= '\uffef':
                space_count += 2
            else:
                space_count += 1
        return space_count

    # ---------------- 聊天记录保存/清空 ----------------
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

    # ---------------- 登录 ----------------
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

            send_json(self.client_socket, {"username": self.username})

            self.is_connected = True
            self.login_btn.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.server_entry.config(state=tk.DISABLED)
            self.add_message(f"[{self.get_current_time()}] 成功连接服务器：{self.server_host}")
            self.add_message(f"[{self.get_current_time()}] 登录成功，开始聊天吧！")

            recv_thread = threading.Thread(target=self.receive_messages, daemon=True)
            recv_thread.start()

        except Exception as e:
            messagebox.showerror("错误", f"连接服务器失败：{e}")

    def _reset_login_ui(self):
        self.is_connected = False
        self.login_btn.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        self.server_entry.config(state=tk.NORMAL)

    # ---------------- 接收消息 ----------------
    def receive_messages(self):
        msg_buffer = ""
        while self.is_connected:
            try:
                chunk = self.client_socket.recv(65536).decode('utf-8', errors='ignore')
                if not chunk:
                    break
                msg_buffer += chunk

                while '\n' in msg_buffer:
                    line, msg_buffer = msg_buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg_data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        self._dispatch_message(msg_data)
                    except Exception as e:
                        self.add_message(f"[{self.get_current_time()}] 处理消息出错：{e}")

            except socket.timeout:
                continue
            except Exception as e:
                self.add_message(f"[{self.get_current_time()}] 接收消息异常：{str(e)}")
                break

        self.is_connected = False
        self.add_message(f"[{self.get_current_time()}] 与服务器断开连接！")
        self.root.after(0, self._reset_login_ui)

    def _dispatch_message(self, msg_data):
        msg_type = msg_data.get('type')
        if msg_type == 'message':
            self.add_message(f"[{msg_data['time']}] {msg_data['sender']}：{msg_data['content']}")
        elif msg_type == 'system':
            self.add_message(f"[{msg_data['time']}] 系统提示：{msg_data['content']}")
        elif msg_type == 'notice':
            self.add_message(f"[{msg_data['time']}] 服务器公告：{msg_data['content']}")
        elif msg_type == 'error':
            self.msg_queue.put(('popup', {'title': '服务器消息', 'msg': msg_data.get('msg', '未知错误')}))
        elif msg_type == 'file_offer':
            self._handle_file_offer(msg_data)
        elif msg_type == 'file_download_start':
            self._handle_download_start(msg_data)
        elif msg_type == 'file_download_chunk':
            self._handle_download_chunk(msg_data)
        elif msg_type == 'file_download_end':
            self._handle_download_end(msg_data)
        elif msg_type == 'file_download_error':
            fid = msg_data.get('file_id')
            self.downloading.discard(fid)
            self.file_downloads.pop(fid, None)
            self.add_message(f"[{self.get_current_time()}] 下载失败：{msg_data.get('msg', '未知错误')}")

    # ---------------- 文件：接收与下载 ----------------
    def _handle_file_offer(self, msg_data):
        file_id = msg_data['file_id']
        filename = msg_data['filename']
        size = msg_data['size']
        sender = msg_data['sender']
        time_str = msg_data.get('time', self.get_current_time())

        self.file_offers[file_id] = {'filename': filename, 'size': size}
        self.add_file_message(
            time_str=time_str,
            sender=sender,
            file_id=file_id,
            filename=filename,
            size=size,
            is_own=False
        )

    def _handle_download_start(self, msg_data):
        file_id = msg_data['file_id']
        if file_id not in self.downloading:
            # 不是本客户端请求的下载，忽略
            return
        self.file_downloads[file_id] = {
            'filename': msg_data['filename'],
            'total': msg_data['total_chunks'],
            'size': msg_data.get('size', 0),
            'chunks': {}
        }
        self.add_message(f"[{self.get_current_time()}] 正在下载：{msg_data['filename']} ...")

    def _handle_download_chunk(self, msg_data):
        file_id = msg_data['file_id']
        info = self.file_downloads.get(file_id)
        if not info:
            return
        info['chunks'][msg_data['index']] = msg_data['data']

    def _handle_download_end(self, msg_data):
        file_id = msg_data['file_id']
        info = self.file_downloads.pop(file_id, None)
        self.downloading.discard(file_id)
        if not info:
            return

        total = info['total']
        if len(info['chunks']) != total:
            self.add_message(f"[{self.get_current_time()}] 下载失败：数据不完整（{len(info['chunks'])}/{total}）")
            return

        try:
            # 按索引顺序拼接
            raw = b''.join(base64.b64decode(info['chunks'][i]) for i in range(total))
        except Exception as e:
            self.add_message(f"[{self.get_current_time()}] 下载失败：数据解码错误 {e}")
            return

        # 放入队列让主线程弹出保存对话框
        self.msg_queue.put(('save_file', {
            'filename': info['filename'],
            'data': raw
        }))

    def request_file_download(self, file_id, filename):
        """用户点击文件消息时触发"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录服务器！")
            return
        if file_id in self.downloading:
            messagebox.showinfo("提示", "该文件正在下载中，请稍候...")
            return
        self.downloading.add(file_id)
        send_json(self.client_socket, {
            'type': 'file_download_request',
            'file_id': file_id
        })
        self.add_message(f"[{self.get_current_time()}] 已请求下载：{filename}")

    # ---------------- 文件：发送 ----------------
    def choose_and_send_file(self):
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录服务器！")
            return
        file_path = filedialog.askopenfilename(title="选择要发送的文件")
        if not file_path:
            return

        try:
            size = os.path.getsize(file_path)
        except OSError as e:
            messagebox.showerror("错误", f"无法读取文件：{e}")
            return

        if size == 0:
            messagebox.showwarning("提示", "不能发送空文件")
            return
        if size > MAX_FILE_SIZE:
            messagebox.showwarning("提示", f"文件过大（最大 {format_size(MAX_FILE_SIZE)}）")
            return

        filename = os.path.basename(file_path)
        file_id = uuid.uuid4().hex

        try:
            with open(file_path, 'rb') as f:
                data = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败：{e}")
            return

        # 在 UI 中立即显示自己发的文件消息（点击可打开本地文件）
        self.add_file_message(
            time_str=self.get_current_time(),
            sender=self.username,
            file_id=file_id,
            filename=filename,
            size=size,
            is_own=True,
            local_path=file_path
        )

        # 启动后台上传线程，避免卡界面
        t = threading.Thread(
            target=self._upload_file_worker,
            args=(file_id, filename, data),
            daemon=True
        )
        t.start()

    def _upload_file_worker(self, file_id, filename, data):
        size = len(data)
        total = (size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # 1. 发送开始
        if not send_json(self.client_socket, {
            'type': 'file_upload_start',
            'file_id': file_id,
            'filename': filename,
            'size': size,
            'total_chunks': total
        }):
            self.add_message(f"[{self.get_current_time()}] 文件上传失败：连接异常")
            return

        # 2. 发送分块
        for i in range(total):
            chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            b64 = base64.b64encode(chunk).decode('ascii')
            if not send_json(self.client_socket, {
                'type': 'file_upload_chunk',
                'file_id': file_id,
                'index': i,
                'data': b64
            }):
                self.add_message(f"[{self.get_current_time()}] 文件上传中断：连接异常")
                return

        # 3. 发送结束
        if send_json(self.client_socket, {
            'type': 'file_upload_end',
            'file_id': file_id
        }):
            self.add_message(f"[{self.get_current_time()}] 文件已发送：{filename}")

    def _open_local_file(self, path):
        """点击自己发送的文件消息，用系统默认程序打开"""
        if not os.path.exists(path):
            messagebox.showwarning("提示", f"文件不存在：{path}")
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件：{e}")

    # ---------------- 发送消息 ----------------
    def send_message(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("警告", "请先登录服务器！")
            return

        msg_content = self.msg_text.get("1.0", tk.END).strip()
        if not msg_content:
            messagebox.showinfo("提示", "消息内容不能为空！")
            return

        try:
            msg_data = {
                "type": "message",
                "content": msg_content,
                "sender": self.username,
                "time": self.get_current_time()
            }
            if not send_json(self.client_socket, msg_data):
                messagebox.showerror("错误", "发送消息失败：连接异常")
                return

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
