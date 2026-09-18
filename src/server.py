import socket
import threading
import json
import time
import base64
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
import queue
import os

# 服务器配置
HOST = '0.0.0.0'
PORT = 9999
MAX_FILE_SIZE = 20 * 1024 * 1024          # 单个文件最大 20MB
MAX_STORE_SIZE = 200 * 1024 * 1024        # 服务器文件缓存总上限 200MB
FILE_EXPIRE_SECONDS = 3600                # 文件缓存 1 小时后自动清理

clients = {}               # {用户名: (socket, 地址)}
banned_users = set()       # 被拉黑的用户名集合
banned_ips = set()         # 被封禁的IP地址集合
admins = set()             # 管理员用户名集合
lock = threading.RLock()   # 保护共享数据
server_running = True
server_socket = None
log_queue = queue.Queue()  # 用于线程安全的日志输出
message_queue = queue.Queue()  # 用于消息显示
chat_records = []          # 全局聊天记录存储
log_records = []           # 全局日志记录存储
refresh_event = threading.Event()  # 有列表变化时通知GUI立即刷新
close_requested = threading.Event()  # 客户端请求关闭服务器时通知GUI弹窗
admin_request_queue = queue.Queue()  # 管理员变更请求队列（需服务器GUI确认）

# 文件缓存相关
file_store = {}            # {file_id: {'filename', 'size', 'data', 'sender', 'time', 'ts'}}
upload_sessions = {}       # {file_id: {'filename','size','total_chunks','chunks','received','sender'}}

# 每个 socket 一把发送锁，避免多线程并发 send 造成数据交错
_sock_locks = {}
_sock_locks_guard = threading.Lock()


def _get_sock_lock(sock):
    with _sock_locks_guard:
        lk = _sock_locks.get(id(sock))
        if lk is None:
            lk = threading.Lock()
            _sock_locks[id(sock)] = lk
        return lk


# ---------- 通用工具 ----------
def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    """以「一行一条 JSON」的协议发送数据（线程安全）"""
    try:
        payload = (json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8')
        with _get_sock_lock(sock):
            sock.sendall(payload)
        return True
    except Exception:
        return False


class ServerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("聊天服务器管理控制台")
        self.root.geometry("1300x850")
        self.root.configure(bg='#f0f0f0')
        self.create_widgets()
        self.update_log()
        self.update_messages()
        self.update_user_list()
        self.update_ban_list()
        self.update_ipban_list()
        self.update_admin_list()
        self.check_refresh_event()   # 启动事件触发的即时刷新检查
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 顶部标题
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=50)
        title_frame.pack(fill=tk.X)
        tk.Label(title_frame, text="聊天服务器管理控制台",
                 font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white').pack(pady=10)

        # 公告发送区域
        notice_frame = tk.Frame(self.root, bg='#f0f0f0')
        notice_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(notice_frame, text="服务器公告：", bg='#f0f0f0', font=('Arial', 11)).pack(side=tk.LEFT, padx=5)
        self.notice_entry = tk.Entry(notice_frame, font=('Arial', 11), width=60)
        self.notice_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(notice_frame, text="发送公告", bg='#3498db', fg='white',
                  command=self.send_notice).pack(side=tk.LEFT, padx=5)

        # 主内容区域（左右分栏）
        main_panel = tk.Frame(self.root, bg='#f0f0f0')
        main_panel.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧面板（日志和消息显示）
        left_panel = tk.Frame(main_panel, bg='#f0f0f0')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 日志区域
        log_frame = tk.LabelFrame(left_panel, text="服务器日志", font=('Arial', 11, 'bold'),
                                   bg='#f0f0f0', padx=5, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # 日志操作按钮
        log_btn_frame = tk.Frame(log_frame, bg='#f0f0f0')
        log_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(log_btn_frame, text="保存日志", bg='#27ae60', fg='white',
                  command=self.save_log).pack(side=tk.LEFT, padx=2)
        tk.Button(log_btn_frame, text="清空日志", bg='#e74c3c', fg='white',
                  command=self.clear_log).pack(side=tk.LEFT, padx=2)

        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                   font=('Consolas', 10), bg='white', height=12)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 消息监控区域
        message_frame = tk.LabelFrame(left_panel, text="消息监控", font=('Arial', 11, 'bold'),
                                      bg='#f0f0f0', padx=5, pady=5)
        message_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 聊天记录操作按钮
        chat_btn_frame = tk.Frame(message_frame, bg='#f0f0f0')
        chat_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(chat_btn_frame, text="保存聊天记录", bg='#27ae60', fg='white',
                  command=self.save_chat_records).pack(side=tk.LEFT, padx=2)
        tk.Button(chat_btn_frame, text="清空聊天记录", bg='#e74c3c', fg='white',
                  command=self.clear_chat_records).pack(side=tk.LEFT, padx=2)

        self.message_area = scrolledtext.ScrolledText(message_frame, wrap=tk.WORD,
                                                       font=('Consolas', 10), bg='#f8f9fa', height=8)
        self.message_area.pack(fill=tk.BOTH, expand=True)

        # 管理员广播区域
        broadcast_frame = tk.LabelFrame(left_panel, text="管理员广播", font=('Arial', 11, 'bold'),
                                        bg='#f0f0f0', padx=5, pady=5)
        broadcast_frame.pack(fill=tk.X, pady=5)
        broadcast_input_frame = tk.Frame(broadcast_frame, bg='#f0f0f0')
        broadcast_input_frame.pack(fill=tk.X, pady=5)
        self.broadcast_input = tk.Text(broadcast_input_frame, font=('Arial', 10),
                                       height=3, wrap=tk.WORD, bg='white')
        self.broadcast_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        tk.Button(broadcast_input_frame, text="发送广播", bg='#3498db', fg='white',
                  font=('Arial', 10, 'bold'), command=self.send_broadcast).pack(side=tk.RIGHT, padx=2)
        tk.Button(broadcast_input_frame, text="清空消息", bg='#95a5a6', fg='white',
                  font=('Arial', 10), command=self.clear_message_area).pack(side=tk.RIGHT, padx=2)

        # 右侧面板（管理区域）
        right_panel = tk.Frame(main_panel, bg='#f0f0f0', width=400)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        right_panel.pack_propagate(False)

        # ========== 在线用户列表 ==========
        online_frame = tk.LabelFrame(right_panel, text="在线用户", font=('Arial', 11, 'bold'),
                                     bg='#f0f0f0', padx=5, pady=5)
        online_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        online_list_frame = tk.Frame(online_frame, bg='#f0f0f0')
        online_list_frame.pack(fill=tk.BOTH, expand=True)
        self.user_listbox = tk.Listbox(online_list_frame, font=('Arial', 10),
                                       bg='white', selectmode=tk.SINGLE, height=6)
        self.user_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        user_scrollbar = tk.Scrollbar(online_list_frame)
        user_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.user_listbox.config(yscrollcommand=user_scrollbar.set)
        user_scrollbar.config(command=self.user_listbox.yview)

        # 在线用户操作按钮
        online_btn_frame = tk.Frame(online_frame, bg='#f0f0f0')
        online_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(online_btn_frame, text="踢出", bg='#e67e22', fg='white',
                  command=self.kick_selected_user).pack(side=tk.LEFT, padx=2)
        tk.Button(online_btn_frame, text="拉黑用户", bg='#e74c3c', fg='white',
                  command=self.ban_selected_user).pack(side=tk.LEFT, padx=2)
        tk.Button(online_btn_frame, text="封禁IP", bg='#c0392b', fg='white',
                  command=self.ban_selected_ip).pack(side=tk.LEFT, padx=2)
        tk.Button(online_btn_frame, text="设为管理员", bg='#9b59b6', fg='white',
                  command=self.set_selected_admin).pack(side=tk.LEFT, padx=2)
        tk.Button(online_btn_frame, text="刷新", bg='#3498db', fg='white',
                  command=self.refresh_user_list).pack(side=tk.RIGHT, padx=2)

        # ========== 黑名单列表 ==========
        ban_frame = tk.LabelFrame(right_panel, text="用户黑名单", font=('Arial', 11, 'bold'),
                                  bg='#f0f0f0', padx=5, pady=5)
        ban_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        ban_list_frame = tk.Frame(ban_frame, bg='#f0f0f0')
        ban_list_frame.pack(fill=tk.BOTH, expand=True)
        self.ban_listbox = tk.Listbox(ban_list_frame, font=('Arial', 10),
                                      bg='white', selectmode=tk.SINGLE, height=4)
        self.ban_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ban_scrollbar = tk.Scrollbar(ban_list_frame)
        ban_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ban_listbox.config(yscrollcommand=ban_scrollbar.set)
        ban_scrollbar.config(command=self.ban_listbox.yview)

        # 黑名单操作按钮
        ban_btn_frame = tk.Frame(ban_frame, bg='#f0f0f0')
        ban_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(ban_btn_frame, text="解除拉黑", bg='#27ae60', fg='white',
                  command=self.unban_selected_user).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(ban_btn_frame, text="刷新", bg='#3498db', fg='white',
                  command=self.refresh_ban_list).pack(side=tk.RIGHT)

        # ========== IP封禁列表 ==========
        ipban_frame = tk.LabelFrame(right_panel, text="IP封禁列表", font=('Arial', 11, 'bold'),
                                    bg='#f0f0f0', padx=5, pady=5)
        ipban_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        ipban_list_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        ipban_list_frame.pack(fill=tk.BOTH, expand=True)
        self.ipban_listbox = tk.Listbox(ipban_list_frame, font=('Arial', 10),
                                        bg='white', selectmode=tk.SINGLE, height=4)
        self.ipban_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ipban_scrollbar = tk.Scrollbar(ipban_list_frame)
        ipban_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ipban_listbox.config(yscrollcommand=ipban_scrollbar.set)
        ipban_scrollbar.config(command=self.ipban_listbox.yview)

        # 解除IP封禁按钮 + 刷新
        ipban_btn_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        ipban_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(ipban_btn_frame, text="解除IP封禁", bg='#27ae60', fg='white',
                  command=self.unban_selected_ip).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(ipban_btn_frame, text="刷新", bg='#3498db', fg='white',
                  command=self.refresh_ipban_list).pack(side=tk.RIGHT)

        # 手动封禁IP输入区域
        manual_ip_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        manual_ip_frame.pack(fill=tk.X, pady=5)
        self.ip_entry = tk.Entry(manual_ip_frame, font=('Arial', 10), bg='white')
        self.ip_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(manual_ip_frame, text="手动封禁IP", bg='#e74c3c', fg='white',
                  command=self.ban_ip_manual).pack(side=tk.RIGHT)

        # ========== 管理员列表 ==========
        admin_frame = tk.LabelFrame(right_panel, text="管理员列表", font=('Arial', 11, 'bold'),
                                     bg='#f0f0f0', padx=5, pady=5)
        admin_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        admin_list_frame = tk.Frame(admin_frame, bg='#f0f0f0')
        admin_list_frame.pack(fill=tk.BOTH, expand=True)
        self.admin_listbox = tk.Listbox(admin_list_frame, font=('Arial', 10),
                                        bg='white', selectmode=tk.SINGLE, height=4)
        self.admin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        admin_scrollbar = tk.Scrollbar(admin_list_frame)
        admin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.admin_listbox.config(yscrollcommand=admin_scrollbar.set)
        admin_scrollbar.config(command=self.admin_listbox.yview)

        # 取消管理员按钮
        tk.Button(admin_frame, text="取消管理员", bg='#e67e22', fg='white',
                  command=self.remove_selected_admin).pack(fill=tk.X, pady=5)

        # 底部控制按钮
        bottom_frame = tk.Frame(self.root, bg='#f0f0f0')
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(bottom_frame, text="关闭服务器", bg='#c0392b', fg='white',
                  font=('Arial', 11, 'bold'), command=self.on_closing).pack(side=tk.RIGHT)
        self.status_label = tk.Label(bottom_frame, text="服务器运行中...", font=('Arial', 10),
                                     bg='#f0f0f0', fg='#27ae60')
        self.status_label.pack(side=tk.LEFT)

    # ---------- GUI 辅助方法 ----------
    def log(self, message):
        """添加日志到队列和全局日志记录"""
        log_queue.put(message)
        log_records.append(message)

    def update_log(self):
        try:
            while True:
                message = log_queue.get_nowait()
                self.log_area.insert(tk.END, message + '\n')
                self.log_area.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.update_log)

    def update_messages(self):
        try:
            while True:
                message_data = message_queue.get_nowait()
                formatted_msg = f"[{message_data['time']}] {message_data['sender']}: {message_data['content']}"
                self.message_area.insert(tk.END, formatted_msg + '\n')
                if message_data.get('sender') == '管理员':
                    self.message_area.tag_add('admin', "end-2l", "end-1l")
                    self.message_area.tag_config('admin', foreground='#2980b9', font=('Consolas', 10, 'bold'))
                elif message_data.get('sender') == '系统':
                    self.message_area.tag_add('system', "end-2l", "end-1l")
                    self.message_area.tag_config('system', foreground='#27ae60')
                self.message_area.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.update_messages)

    def send_broadcast(self):
        message = self.broadcast_input.get("1.0", tk.END).strip()
        if message:
            admin_broadcast(message)
            self.broadcast_input.delete("1.0", tk.END)

    def clear_message_area(self):
        self.message_area.delete("1.0", tk.END)

    # ========== 事件触发的即时刷新 + 关闭请求检查 + 管理员变更请求检查 ==========
    def check_refresh_event(self):
        """每 200 毫秒检查一次刷新信号、关闭请求和管理员变更请求"""
        # 列表刷新信号
        if refresh_event.is_set():
            refresh_event.clear()
            self.refresh_user_list()
            self.refresh_ban_list()
            self.refresh_ipban_list()
        # 客户端关闭服务器请求
        if close_requested.is_set():
            close_requested.clear()
            # on_closing 内部会弹窗确认，确认后关闭服务器
            self.on_closing()
        # 管理员变更请求（需服务器GUI确认）
        while True:
            try:
                action, target, requester = admin_request_queue.get_nowait()
            except queue.Empty:
                break
            if action == "new":
                if messagebox.askyesno("管理员变更确认",
                                       f"管理员 {requester} 请求将用户 {target} 设为管理员。\n\n是否同意？"):
                    set_admin(target)
                    log_queue.put(f"[{get_current_time()}] 服务器已同意 {requester} 的请求：将 {target} 设为管理员")
                else:
                    send_system_message(requester, f"服务器已拒绝将 {target} 设为管理员的请求")
                    log_queue.put(f"[{get_current_time()}] 服务器已拒绝 {requester} 的请求：将 {target} 设为管理员")
            elif action == "cancel":
                if messagebox.askyesno("管理员变更确认",
                                       f"管理员 {requester} 请求取消用户 {target} 的管理员权限。\n\n是否同意？"):
                    remove_admin(target)
                    log_queue.put(f"[{get_current_time()}] 服务器已同意 {requester} 的请求：取消 {target} 的管理员权限")
                else:
                    send_system_message(requester, f"服务器已拒绝取消 {target} 管理员权限的请求")
                    log_queue.put(f"[{get_current_time()}] 服务器已拒绝 {requester} 的请求：取消 {target} 的管理员权限")
        self.root.after(200, self.check_refresh_event)

    # ========== 在线用户列表：刷新与定时 ==========
    def refresh_user_list(self):
        """真正执行刷新在线用户列表（可手动/定时/事件触发调用）"""
        with lock:
            current_users = list(clients.keys())
        self.user_listbox.delete(0, tk.END)
        for user in sorted(current_users):
            self.user_listbox.insert(tk.END, user)
        self.status_label.config(text=f"服务器运行中... 在线用户: {len(current_users)}")

    def update_user_list(self):
        """定时调度：每 10 秒刷新一次"""
        self.refresh_user_list()
        self.root.after(10000, self.update_user_list)

    # ========== 用户黑名单：刷新与定时 ==========
    def refresh_ban_list(self):
        """真正执行刷新用户黑名单（可手动/定时/事件触发调用）"""
        with lock:
            current_bans = list(banned_users)
        self.ban_listbox.delete(0, tk.END)
        for user in sorted(current_bans):
            self.ban_listbox.insert(tk.END, user)

    def update_ban_list(self):
        """定时调度：每 10 秒刷新一次"""
        self.refresh_ban_list()
        self.root.after(10000, self.update_ban_list)

    # ========== IP封禁列表：刷新与定时 ==========
    def refresh_ipban_list(self):
        """真正执行刷新IP封禁列表（可手动/定时/事件触发调用）"""
        with lock:
            current_ipbans = list(banned_ips)
        self.ipban_listbox.delete(0, tk.END)
        for ip in sorted(current_ipbans):
            self.ipban_listbox.insert(tk.END, ip)

    def update_ipban_list(self):
        """定时调度：每 10 秒刷新一次"""
        self.refresh_ipban_list()
        self.root.after(10000, self.update_ipban_list)

    # ========== 管理员列表（保持原逻辑，2 秒刷新） ==========
    def update_admin_list(self):
        with lock:
            current_admins = list(admins)
        self.admin_listbox.delete(0, tk.END)
        for admin in sorted(current_admins):
            self.admin_listbox.insert(tk.END, admin)
        self.root.after(2000, self.update_admin_list)

    def get_selected_user(self, listbox):
        selection = listbox.curselection()
        return listbox.get(selection[0]) if selection else None

    def get_user_ip(self, username):
        with lock:
            if username in clients:
                return clients[username][1][0]
        return None

    def kick_selected_user(self):
        username = self.get_selected_user(self.user_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要踢出用户 {username} 吗？"):
                kick_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")

    def ban_selected_user(self):
        username = self.get_selected_user(self.user_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要拉黑用户 {username} 吗？"):
                ban_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")

    def ban_selected_ip(self):
        username = self.get_selected_user(self.user_listbox)
        if username:
            ip = self.get_user_ip(username)
            if ip:
                if messagebox.askyesno("确认", f"确定要封禁用户 {username} 的IP ({ip}) 吗？\n这将踢出所有使用该IP的用户！"):
                    ban_ip(ip)
            else:
                messagebox.showerror("错误", f"无法获取用户 {username} 的IP地址")
        else:
            messagebox.showwarning("提示", "请先选择一个用户")

    def set_selected_admin(self):
        username = self.get_selected_user(self.user_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要将用户 {username} 设为管理员吗？"):
                set_admin(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")

    def remove_selected_admin(self):
        username = self.get_selected_user(self.admin_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要取消用户 {username} 的管理员权限吗？"):
                remove_admin(username)
        else:
            messagebox.showwarning("提示", "请先在管理员列表中选择一个用户")

    def unban_selected_user(self):
        username = self.get_selected_user(self.ban_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要解除用户 {username} 的拉黑吗？"):
                unban_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")

    def unban_selected_ip(self):
        ip = self.get_selected_user(self.ipban_listbox)
        if ip:
            if messagebox.askyesno("确认", f"确定要解除IP {ip} 的封禁吗？"):
                unban_ip(ip)
        else:
            messagebox.showwarning("提示", "请先选择一个IP")

    def ban_ip_manual(self):
        ip = self.ip_entry.get().strip()
        if ip:
            if messagebox.askyesno("确认", f"确定要封禁IP {ip} 吗？"):
                ban_ip(ip)
                self.ip_entry.delete(0, tk.END)
        else:
            messagebox.showwarning("提示", "请输入要封禁的IP地址")

    def send_notice(self):
        """发送服务器公告"""
        notice_content = self.notice_entry.get().strip()
        if not notice_content:
            messagebox.showwarning("提示", "公告内容不能为空！")
            return
        with lock:
            notice_data = {
                "type": "notice",
                "content": notice_content,
                "time": get_current_time()
            }
            # 广播公告给所有在线用户
            for username, (client_socket, addr) in list(clients.items()):
                if not send_json(client_socket, notice_data):
                    self.log(f"[{get_current_time()}] 向 {username} 发送公告失败")
        self.log(f"[{get_current_time()}] 发送公告：{notice_content}")
        self.notice_entry.delete(0, tk.END)

    def save_log(self):
        """保存服务器日志到文件"""
        if not log_records:
            messagebox.showinfo("提示", "日志为空，无需保存")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="保存服务器日志"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(log_records))
                messagebox.showinfo("成功", f"日志已保存到：{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存日志失败：{e}")

    def clear_log(self):
        """清空服务器日志"""
        if messagebox.askyesno("确认", "确定要清空服务器日志吗？"):
            global log_records
            log_records = []
            self.log_area.delete(1.0, tk.END)
            self.log(f"[{get_current_time()}] 服务器日志已清空")

    def save_chat_records(self):
        """保存聊天记录到文件"""
        if not chat_records:
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
                    f.write('\n'.join(chat_records))
                messagebox.showinfo("成功", f"聊天记录已保存到：{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存聊天记录失败：{e}")

    def clear_chat_records(self):
        """清空聊天记录"""
        if messagebox.askyesno("确认", "确定要清空聊天记录吗？"):
            global chat_records
            chat_records = []
            self.message_area.delete(1.0, tk.END)
            self.log(f"[{get_current_time()}] 聊天记录已清空")

    def on_closing(self):
        if messagebox.askyesno("确认", "确定要关闭服务器吗？"):
            self.log("正在关闭服务器...")
            shutdown_server()
            self.root.after(1000, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ---------- 核心功能函数 ----------
def send_system_message(target_username, content):
    """发送系统消息给指定用户"""
    with lock:
        if target_username in clients:
            msg_data = {
                "type": "system",
                "content": content,
                "time": get_current_time()
            }
            if not send_json(clients[target_username][0], msg_data):
                log_queue.put(f"[{get_current_time()}] 发送系统消息给 {target_username} 失败")


def broadcast_message(sender, message):
    """广播消息给所有在线用户（除发送者外）"""
    with lock:
        msg_data = {
            "type": "message",
            "sender": sender,
            "content": message,
            "time": get_current_time()
        }

        # 记录聊天记录
        chat_record = f"[{msg_data['time']}] {sender}：{message}"
        chat_records.append(chat_record)

        for username, (client_socket, addr) in list(clients.items()):
            if username != sender:
                if not send_json(client_socket, msg_data):
                    log_queue.put(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                    clients.pop(username, None)
        # 将消息添加到消息队列供GUI显示
        message_queue.put(msg_data)


def admin_broadcast(message):
    """管理员广播消息"""
    with lock:
        msg_data = {
            "type": "message",
            "sender": "管理员",
            "content": message,
            "time": get_current_time()
        }

        # 记录聊天记录
        chat_record = f"[{msg_data['time']}] 管理员：{message}"
        chat_records.append(chat_record)

        for username, (client_socket, addr) in list(clients.items()):
            if not send_json(client_socket, msg_data):
                log_queue.put(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                clients.pop(username, None)
        log_queue.put(f"[{get_current_time()}] 管理员广播: {message}")
        message_queue.put(msg_data)


# ---------- 文件相关 ----------
def handle_file_upload_start(username, msg_data):
    file_id = msg_data.get('file_id')
    filename = msg_data.get('filename', 'unknown')
    try:
        size = int(msg_data.get('size', 0))
        total = int(msg_data.get('total_chunks', 0))
    except (TypeError, ValueError):
        return
    if not file_id or total <= 0:
        return
    if size > MAX_FILE_SIZE:
        send_system_message(username, f"文件过大（最大 {format_size(MAX_FILE_SIZE)}），已拒绝")
        return
    with lock:
        # 统计当前占用
        current_total = sum(f['size'] for f in file_store.values())
        pending = sum(s['size'] for s in upload_sessions.values())
        if current_total + pending + size > MAX_STORE_SIZE:
            send_system_message(username, "服务器文件缓存空间不足，请稍后再试")
            return
        upload_sessions[file_id] = {
            'filename': filename,
            'size': size,
            'total_chunks': total,
            'chunks': [None] * total,
            'received': 0,
            'sender': username
        }


def handle_file_upload_chunk(username, msg_data):
    file_id = msg_data.get('file_id')
    try:
        index = int(msg_data.get('index', -1))
    except (TypeError, ValueError):
        return
    data_b64 = msg_data.get('data', '')
    with lock:
        session = upload_sessions.get(file_id)
        if not session or session['sender'] != username:
            return
        if not (0 <= index < session['total_chunks']):
            return
        if session['chunks'][index] is None:
            session['chunks'][index] = data_b64
            session['received'] += 1


def handle_file_upload_end(username, msg_data):
    file_id = msg_data.get('file_id')
    with lock:
        session = upload_sessions.pop(file_id, None)
    if not session or session['sender'] != username:
        return
    if session['received'] != session['total_chunks']:
        send_system_message(username, "文件上传不完整，已取消")
        return
    try:
        raw = b''.join(base64.b64decode(c) for c in session['chunks'])
    except Exception as e:
        send_system_message(username, f"文件数据损坏：{e}")
        return

    now = time.time()
    with lock:
        file_store[file_id] = {
            'filename': session['filename'],
            'size': len(raw),
            'data': raw,
            'sender': username,
            'time': get_current_time(),
            'ts': now
        }
        targets = [(u, s) for u, (s, a) in clients.items() if u != username]

    # 广播文件摘要给其他在线用户（让他们点击下载）
    offer = {
        'type': 'file_offer',
        'file_id': file_id,
        'filename': session['filename'],
        'size': len(raw),
        'sender': username,
        'time': get_current_time()
    }
    for _u, sock in targets:
        send_json(sock, offer)

    size_str = format_size(len(raw))
    info = f"[{get_current_time()}] {username} 上传文件：{session['filename']}（{size_str}）"
    chat_records.append(info)
    log_queue.put(info)
    message_queue.put({
        'time': get_current_time(),
        'sender': username,
        'content': f"[文件] {session['filename']}（{size_str}）"
    })


def _send_file_to_client(target_sock, info, file_id):
    """在单独线程中把文件分块发送给指定客户端"""
    data = info['data']
    chunk_size = 3 * 1024  # 二进制 3KB，base64 后约 4KB
    total = (len(data) + chunk_size - 1) // chunk_size
    if not send_json(target_sock, {
        'type': 'file_download_start',
        'file_id': file_id,
        'filename': info['filename'],
        'size': info['size'],
        'total_chunks': total
    }):
        return
    for i in range(total):
        chunk = data[i * chunk_size:(i + 1) * chunk_size]
        if not send_json(target_sock, {
            'type': 'file_download_chunk',
            'file_id': file_id,
            'index': i,
            'data': base64.b64encode(chunk).decode('ascii')
        }):
            return
    send_json(target_sock, {'type': 'file_download_end', 'file_id': file_id})


def handle_file_download_request(username, msg_data):
    file_id = msg_data.get('file_id')
    with lock:
        info = file_store.get(file_id)
        target_sock = clients.get(username, (None,))[0]
    if not info:
        send_system_message(username, "文件不存在或已过期")
        return
    if not target_sock:
        return
    t = threading.Thread(target=_send_file_to_client,
                         args=(target_sock, info, file_id), daemon=True)
    t.start()
    log_queue.put(f"[{get_current_time()}] {username} 请求下载文件：{info['filename']}")


def cleanup_file_store():
    """后台线程：定期清理过期或超量文件"""
    while True:
        time.sleep(300)
        try:
            now = time.time()
            with lock:
                expired = [fid for fid, info in file_store.items()
                           if now - info.get('ts', now) > FILE_EXPIRE_SECONDS]
                for fid in expired:
                    file_store.pop(fid, None)
                if expired:
                    log_queue.put(f"[{get_current_time()}] 已清理 {len(expired)} 个过期文件缓存")

                total = sum(info['size'] for info in file_store.values())
                if total > MAX_STORE_SIZE:
                    items = sorted(file_store.items(), key=lambda kv: kv[1].get('ts', 0))
                    removed = 0
                    for fid, info in items:
                        if total <= MAX_STORE_SIZE * 0.8:
                            break
                        total -= info['size']
                        file_store.pop(fid, None)
                        removed += 1
                    if removed:
                        log_queue.put(f"[{get_current_time()}] 文件缓存超限，已清理 {removed} 个最旧文件")
        except Exception:
            pass


def kick_user(target_username):
    """踢出指定用户（仅踢出，不拉黑）"""
    with lock:
        if target_username not in clients:
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 不存在或已离线")
            return False
        client_socket, addr = clients[target_username]
        send_json(client_socket, {
            "type": "system",
            "content": "你已被管理员踢出服务器！",
            "time": get_current_time()
        })
        try:
            client_socket.close()
        except Exception:
            pass
        clients.pop(target_username, None)
    broadcast_message("系统", f"{target_username} 已被管理员踢出！当前在线人数：{len(clients)}")
    log_queue.put(f"[{get_current_time()}] 已踢出用户 {target_username}")
    refresh_event.set()   # 触发GUI立即刷新
    return True


def ban_user(target_username):
    """拉黑用户：加入黑名单，若在线则立即踢出"""
    kicked = False
    with lock:
        banned_users.add(target_username)
        if target_username in clients:
            client_socket, addr = clients[target_username]
            send_json(client_socket, {
                "type": "system",
                "content": "你已被管理员拉黑，无法继续使用！",
                "time": get_current_time()
            })
            try:
                client_socket.close()
            except Exception:
                pass
            clients.pop(target_username, None)
            kicked = True
    if kicked:
        broadcast_message("系统", f"{target_username} 已被管理员拉黑并踢出！当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被拉黑并踢出")
    else:
        log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被拉黑（不在线）")
    refresh_event.set()   # 触发GUI立即刷新


def unban_user(target_username):
    """解除拉黑"""
    with lock:
        if target_username in banned_users:
            banned_users.remove(target_username)
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被解除拉黑")
        else:
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 不在黑名单中")
    refresh_event.set()   # 触发GUI立即刷新


def ban_ip(ip_address):
    """封禁IP地址：加入IP黑名单，若该IP有在线用户则全部踢出"""
    kicked_any = False
    with lock:
        banned_ips.add(ip_address)
        to_remove = []
        for username, (client_socket, addr) in list(clients.items()):
            if addr[0] == ip_address:
                send_json(client_socket, {
                    "type": "system",
                    "content": "你的IP已被封禁，连接即将断开。",
                    "time": get_current_time()
                })
                try:
                    client_socket.close()
                except Exception:
                    pass
                to_remove.append(username)
                kicked_any = True
        for username in to_remove:
            clients.pop(username, None)
    if kicked_any:
        broadcast_message("系统", f"IP {ip_address} 已被封禁，相关用户已断开。当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被封禁，并踢出所有在线用户")
    else:
        log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被封禁（无在线用户）")
    refresh_event.set()   # 触发GUI立即刷新


def unban_ip(ip_address):
    """解除IP封禁"""
    with lock:
        if ip_address in banned_ips:
            banned_ips.remove(ip_address)
            log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被解除封禁")
        else:
            log_queue.put(f"[{get_current_time()}] IP {ip_address} 不在封禁列表中")
    refresh_event.set()   # 触发GUI立即刷新


def set_admin(username):
    """将用户设为管理员"""
    should_notify = False
    with lock:
        if username not in admins:
            admins.add(username)
            should_notify = True
        else:
            log_queue.put(f"[{get_current_time()}] 用户 {username} 已经是管理员")
            return
    if should_notify:
        # 给管理员本人发送私密通知
        send_system_message(
            username,
            "你已经被设为管理员。可用指令：\n"
            "kick 用户名 —— 踢出用户\n"
            "ban 用户名 —— 拉黑用户\n"
            "unban 用户名 —— 解除拉黑\n"
            "banip ipmode IP —— 封禁指定IP\n"
            "banip usermode 用户名 —— 封禁指定用户的IP\n"
            "unbanip ipmode IP —— 解除封禁指定IP\n"
            "unbanip usermode 用户名 —— 解除封禁指定用户的IP\n"
            "admin new 用户名 —— 请求将用户设为管理员（需服务器确认）\n"
            "admin cancel 用户名 —— 请求取消用户的管理员权限（需服务器确认）\n"
            "close —— 请求关闭服务器"
        )
        # 广播给所有人
        broadcast_message("系统", f"{username} 已被设为管理员")
        log_queue.put(f"[{get_current_time()}] 用户 {username} 被设为管理员")


def remove_admin(username):
    """取消用户的管理员权限"""
    should_notify = False
    with lock:
        if username in admins:
            admins.remove(username)
            should_notify = True
        else:
            log_queue.put(f"[{get_current_time()}] 用户 {username} 不是管理员")
            return
    if should_notify:
        # 给原管理员本人发送通知
        send_system_message(username, "你的管理员权限已被取消")
        # 广播给所有人
        broadcast_message("系统", f"{username} 的管理员权限已被取消")
        log_queue.put(f"[{get_current_time()}] 用户 {username} 的管理员权限被取消")


def shutdown_server():
    """关闭服务器"""
    global server_running, server_socket
    with lock:
        if not server_running:
            return
        server_running = False
        shutdown_msg = {
            "type": "system",
            "content": "服务器即将关闭，连接断开。",
            "time": get_current_time()
        }
        for username, (client_socket, addr) in list(clients.items()):
            send_json(client_socket, shutdown_msg)
            try:
                client_socket.close()
            except Exception:
                pass
        clients.clear()
        file_store.clear()
        upload_sessions.clear()
    if server_socket:
        try:
            server_socket.close()
        except Exception:
            pass
    log_queue.put(f"[{get_current_time()}] 服务器关闭程序已执行。")


# ---------- 客户端消息处理 ----------
def _process_message(username, msg_data):
    """处理一条来自客户端的消息"""
    msg_type = msg_data.get('type')

    # 文件上传相关
    if msg_type == 'file_upload_start':
        handle_file_upload_start(username, msg_data)
        return
    if msg_type == 'file_upload_chunk':
        handle_file_upload_chunk(username, msg_data)
        return
    if msg_type == 'file_upload_end':
        handle_file_upload_end(username, msg_data)
        return
    if msg_type == 'file_download_request':
        handle_file_download_request(username, msg_data)
        return

    if msg_type != 'message':
        return

    content = msg_data.get("content", "")
    if not isinstance(content, str):
        content = str(content)

    with lock:
        is_admin = username in admins

    if not is_admin:
        broadcast_message(username, content)
        return

    stripped = content.strip()

    # ============ 关闭服务器请求 ============
    if stripped == "close":
        send_system_message(username, "已发送关闭服务器请求，等待服务器管理员确认...")
        log_queue.put(f"[{get_current_time()}] 管理员 {username} 请求关闭服务器，已通知GUI弹窗确认")
        close_requested.set()

    # ============ 请求将用户设为管理员（需服务器确认） ============
    elif stripped.startswith("admin new "):
        parts = stripped.split()
        if len(parts) == 3:
            target = parts[2]
            admin_request_queue.put(("new", target, username))
            send_system_message(username, f"已发送将 {target} 设为管理员的请求，等待服务器确认...")
            log_queue.put(f"[{get_current_time()}] 管理员 {username} 请求将 {target} 设为管理员（等待GUI确认）")
        else:
            send_system_message(username, "格式错误，请使用: admin new 用户名")

    # ============ 请求取消用户管理员权限（需服务器确认） ============
    elif stripped.startswith("admin cancel "):
        parts = stripped.split()
        if len(parts) == 3:
            target = parts[2]
            admin_request_queue.put(("cancel", target, username))
            send_system_message(username, f"已发送取消 {target} 管理员权限的请求，等待服务器确认...")
            log_queue.put(f"[{get_current_time()}] 管理员 {username} 请求取消 {target} 的管理员权限（等待GUI确认）")
        else:
            send_system_message(username, "格式错误，请使用: admin cancel 用户名")

    # ============ 踢人命令 ============
    elif stripped.startswith("kick "):
        parts = stripped.split()
        if len(parts) == 2:
            kick_user(parts[1])
        else:
            send_system_message(username, "格式错误，请使用: kick 用户名")

    # ============ 拉黑命令 ============
    elif stripped.startswith("ban "):
        parts = stripped.split()
        if len(parts) == 2:
            ban_user(parts[1])
        else:
            send_system_message(username, "格式错误，请使用: ban 用户名")

    # ============ 解除拉黑命令 ============
    elif stripped.startswith("unban "):
        parts = stripped.split()
        if len(parts) == 2:
            target = parts[1]
            unban_user(target)
            send_system_message(username, f"已解除对用户 {target} 的拉黑")
        else:
            send_system_message(username, "格式错误，请使用: unban 用户名")

    # ============ 封禁IP命令 ============
    elif stripped.startswith("banip "):
        parts = stripped.split()
        if len(parts) == 3:
            mode = parts[1]
            target = parts[2]
            if mode == "ipmode":
                ban_ip(target)
                send_system_message(username, f"已封禁IP：{target}")
            elif mode == "usermode":
                with lock:
                    ip = clients[target][1][0] if target in clients else None
                if ip:
                    ban_ip(ip)
                    send_system_message(username, f"已封禁用户 {target} 的IP：{ip}")
                else:
                    send_system_message(username, f"无法封禁：用户 {target} 不在线或不存在")
            else:
                send_system_message(username, "格式错误，请使用: banip ipmode IP 或 banip usermode 用户名")
        else:
            send_system_message(username, "格式错误，请使用: banip ipmode IP 或 banip usermode 用户名")

    # ============ 解除IP封禁命令 ============
    elif stripped.startswith("unbanip "):
        parts = stripped.split()
        if len(parts) == 3:
            mode = parts[1]
            target = parts[2]
            if mode == "ipmode":
                unban_ip(target)
                send_system_message(username, f"已解除封禁IP：{target}")
            elif mode == "usermode":
                with lock:
                    ip = clients[target][1][0] if target in clients else None
                if ip:
                    unban_ip(ip)
                    send_system_message(username, f"已解除封禁用户 {target} 的IP：{ip}")
                else:
                    send_system_message(username, f"无法解除：用户 {target} 不在线或不存在")
            else:
                send_system_message(username, "格式错误，请使用: unbanip ipmode IP 或 unbanip usermode 用户名")
        else:
            send_system_message(username, "格式错误，请使用: unbanip ipmode IP 或 unbanip usermode 用户名")

    else:
        # 普通消息
        broadcast_message(username, content)


def handle_client(client_socket, addr):
    """处理单个客户端连接"""
    username = None
    client_ip = addr[0]
    buffer = ""          # 按行分包的接收缓冲

    def read_message(timeout=None):
        """读取下一条完整 JSON 消息；返回 None 表示连接断开或超时"""
        nonlocal buffer
        try:
            client_socket.settimeout(timeout)
        except OSError:
            return None
        while '\n' not in buffer:
            try:
                chunk = client_socket.recv(65536).decode('utf-8', errors='ignore')
            except socket.timeout:
                return None
            except OSError:
                return None
            if not chunk:
                return None
            buffer += chunk
        line, buffer = buffer.split('\n', 1)
        line = line.strip()
        if not line:
            return {}
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {}

    try:
        # ---------- 首先检查IP是否被封禁 ----------
        with lock:
            ip_banned = client_ip in banned_ips
        if ip_banned:
            send_json(client_socket, {"type": "error", "msg": "你的IP已被封禁，无法连接！"})
            return

        # ---------- 接收用户名 ----------
        login_data = read_message(timeout=30)
        if not login_data or "username" not in login_data:
            return
        username = str(login_data["username"]).strip()
        if not username:
            return

        with lock:
            banned = username in banned_users
            duplicated = username in clients

        if banned:
            send_json(client_socket, {"type": "error", "msg": "你已被拉黑，无法登录！"})
            return
        if duplicated:
            send_json(client_socket, {"type": "error", "msg": "用户名已存在！"})
            return

        with lock:
            clients[username] = (client_socket, addr)

        broadcast_message("系统", f"{username} 已上线！当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] {username} ({addr}) 已连接，当前在线：{len(clients)}")
        refresh_event.set()   # 有用户加入，立即刷新在线用户列表

        # ---------- 消息主循环 ----------
        while server_running:
            msg_data = read_message()
            if msg_data is None:
                break
            if not msg_data:
                continue
            try:
                _process_message(username, msg_data)
            except Exception as e:
                log_queue.put(f"[{get_current_time()}] 处理 {username} 的消息出错：{e}")

    except Exception as e:
        log_queue.put(f"[{get_current_time()}] 处理客户端 {addr} 时出错：{e}")
    finally:
        # 清理该用户未完成的上传会话
        if username:
            with lock:
                to_remove = [fid for fid, s in upload_sessions.items() if s['sender'] == username]
                for fid in to_remove:
                    upload_sessions.pop(fid, None)
        try:
            client_socket.close()
        except Exception:
            pass
        if username:
            removed = False
            with lock:
                if username in clients:
                    clients.pop(username, None)
                    removed = True
            if removed:
                broadcast_message("系统", f"{username} 已下线！当前在线人数：{len(clients)}")
                log_queue.put(f"[{get_current_time()}] {username} ({addr}) 已断开，当前在线：{len(clients)}")
                refresh_event.set()   # 有用户离开，立即刷新在线用户列表


def start_server():
    global server_socket, server_running
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    log_queue.put(f"[{get_current_time()}] 服务器已启动，监听地址：{HOST}:{PORT}")

    # 启动文件缓存清理线程
    cleaner = threading.Thread(target=cleanup_file_store, daemon=True)
    cleaner.start()

    try:
        while server_running:
            server_socket.settimeout(1.0)
            try:
                client_socket, addr = server_socket.accept()
                client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if server_running:
                    log_queue.put(f"[{get_current_time()}] accept 错误：{e}")
    except Exception as e:
        log_queue.put(f"[{get_current_time()}] 服务器错误：{e}")
    finally:
        shutdown_server()


def run_server_with_gui():
    """运行带GUI的服务器"""
    # 启动服务器线程
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    # 启动GUI
    gui = ServerGUI()
    gui.run()


if __name__ == "__main__":
    run_server_with_gui()
