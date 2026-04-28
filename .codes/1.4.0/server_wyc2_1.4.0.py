import socket
import threading
import json
import time
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import queue

# 服务器配置
HOST = '0.0.0.0'
PORT = 9999
clients = {}               # {用户名: (socket, 地址)}
banned_users = set()       # 被拉黑的用户名集合
banned_ips = set()         # 被封禁的IP地址集合
admins = set()             # 管理员用户名集合
lock = threading.Lock()    # 保护共享数据
server_running = True
server_socket = None
log_queue = queue.Queue()  # 用于线程安全的日志输出
message_queue = queue.Queue()  # 用于消息显示


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
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 顶部标题
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=50)
        title_frame.pack(fill=tk.X)
        tk.Label(title_frame, text="聊天服务器管理控制台",
                 font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white').pack(pady=10)

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
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                   font=('Consolas', 10), bg='white', height=12)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 消息监控区域
        message_frame = tk.LabelFrame(left_panel, text="消息监控", font=('Arial', 11, 'bold'),
                                      bg='#f0f0f0', padx=5, pady=5)
        message_frame.pack(fill=tk.BOTH, expand=True, pady=5)
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
        tk.Button(ban_frame, text="解除拉黑", bg='#27ae60', fg='white',
                  command=self.unban_selected_user).pack(fill=tk.X, pady=5)

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

        # 解除IP封禁按钮
        tk.Button(ipban_frame, text="解除IP封禁", bg='#27ae60', fg='white',
                  command=self.unban_selected_ip).pack(fill=tk.X, pady=5)

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
        log_queue.put(message)

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

    def update_user_list(self):
        with lock:
            current_users = list(clients.keys())
        self.user_listbox.delete(0, tk.END)
        for user in sorted(current_users):
            self.user_listbox.insert(tk.END, user)
        self.status_label.config(text=f"服务器运行中... 在线用户: {len(current_users)}")
        self.root.after(2000, self.update_user_list)

    def update_ban_list(self):
        with lock:
            current_bans = list(banned_users)
        self.ban_listbox.delete(0, tk.END)
        for user in sorted(current_bans):
            self.ban_listbox.insert(tk.END, user)
        self.root.after(2000, self.update_ban_list)

    def update_ipban_list(self):
        with lock:
            current_ipbans = list(banned_ips)
        self.ipban_listbox.delete(0, tk.END)
        for ip in sorted(current_ipbans):
            self.ipban_listbox.insert(tk.END, ip)
        self.root.after(2000, self.update_ipban_list)

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

    def on_closing(self):
        if messagebox.askyesno("确认", "确定要关闭服务器吗？"):
            self.log("正在关闭服务器...")
            shutdown_server()
            self.root.after(1000, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ---------- 核心功能函数 ----------
def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send_system_message(target_username, content):
    """发送系统消息给指定用户"""
    with lock:
        if target_username in clients:
            msg_data = {
                "type": "system",
                "content": content,
                "time": get_current_time()
            }
            msg_json = json.dumps(msg_data, ensure_ascii=False)
            try:
                clients[target_username][0].send(msg_json.encode('utf-8'))
            except:
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
        msg_json = json.dumps(msg_data, ensure_ascii=False)
        for username, (client_socket, addr) in list(clients.items()):
            if username != sender:
                try:
                    client_socket.send(msg_json.encode('utf-8'))
                except:
                    log_queue.put(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                    del clients[username]
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
        msg_json = json.dumps(msg_data, ensure_ascii=False)
        for username, (client_socket, addr) in list(clients.items()):
            try:
                client_socket.send(msg_json.encode('utf-8'))
            except:
                log_queue.put(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                del clients[username]
        log_queue.put(f"[{get_current_time()}] 管理员广播: {message}")
        message_queue.put(msg_data)


def kick_user(target_username):
    """踢出指定用户（仅踢出，不拉黑）"""
    with lock:
        if target_username not in clients:
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 不存在或已离线")
            return False
        client_socket, addr = clients[target_username]
        try:
            kick_msg = json.dumps({
                "type": "system",
                "content": "你已被管理员踢出服务器！",
                "time": get_current_time()
            }, ensure_ascii=False)
            client_socket.send(kick_msg.encode('utf-8'))
        except:
            pass
        try:
            client_socket.close()
        except:
            pass
        del clients[target_username]
    broadcast_message("系统", f"{target_username} 已被管理员踢出！当前在线人数：{len(clients)}")
    log_queue.put(f"[{get_current_time()}] 已踢出用户 {target_username}")
    return True


def ban_user(target_username):
    """拉黑用户：加入黑名单，若在线则立即踢出"""
    kicked = False
    with lock:
        banned_users.add(target_username)
        if target_username in clients:
            client_socket, addr = clients[target_username]
            try:
                ban_msg = json.dumps({
                    "type": "system",
                    "content": "你已被管理员拉黑，无法继续使用！",
                    "time": get_current_time()
                }, ensure_ascii=False)
                client_socket.send(ban_msg.encode('utf-8'))
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
            del clients[target_username]
            kicked = True
    if kicked:
        broadcast_message("系统", f"{target_username} 已被管理员拉黑并踢出！当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被拉黑并踢出")
    else:
        log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被拉黑（不在线）")


def unban_user(target_username):
    """解除拉黑"""
    with lock:
        if target_username in banned_users:
            banned_users.remove(target_username)
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 已被解除拉黑")
        else:
            log_queue.put(f"[{get_current_time()}] 用户 {target_username} 不在黑名单中")


def ban_ip(ip_address):
    """封禁IP地址：加入IP黑名单，若该IP有在线用户则全部踢出"""
    kicked_any = False
    with lock:
        banned_ips.add(ip_address)
        to_remove = []
        for username, (client_socket, addr) in list(clients.items()):
            if addr[0] == ip_address:
                try:
                    ban_msg = json.dumps({
                        "type": "system",
                        "content": "你的IP已被封禁，连接即将断开。",
                        "time": get_current_time()
                    }, ensure_ascii=False)
                    client_socket.send(ban_msg.encode('utf-8'))
                except:
                    pass
                try:
                    client_socket.close()
                except:
                    pass
                to_remove.append(username)
                kicked_any = True
        for username in to_remove:
            del clients[username]
    if kicked_any:
        broadcast_message("系统", f"IP {ip_address} 已被封禁，相关用户已断开。当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被封禁，并踢出所有在线用户")
    else:
        log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被封禁（无在线用户）")


def unban_ip(ip_address):
    """解除IP封禁"""
    with lock:
        if ip_address in banned_ips:
            banned_ips.remove(ip_address)
            log_queue.put(f"[{get_current_time()}] IP {ip_address} 已被解除封禁")
        else:
            log_queue.put(f"[{get_current_time()}] IP {ip_address} 不在封禁列表中")


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
        send_system_message(username, "你已经被设为管理员，输入“kick 用户名”踢人，输入“ban 用户名”拉黑")
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
        msg_json = json.dumps(shutdown_msg, ensure_ascii=False)
        for username, (client_socket, addr) in list(clients.items()):
            try:
                client_socket.send(msg_json.encode('utf-8'))
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
        clients.clear()
    if server_socket:
        server_socket.close()
    log_queue.put(f"[{get_current_time()}] 服务器关闭程序已执行。")


def handle_client(client_socket, addr):
    username = None
    last_msg_time = time.time()
    char_count = 0
    client_ip = addr[0]

    # 首先检查IP是否被封禁
    with lock:
        if client_ip in banned_ips:
            try:
                resp = json.dumps({
                    "type": "error",
                    "msg": "你的IP已被封禁，无法连接！"
                }, ensure_ascii=False)
                client_socket.send(resp.encode('utf-8'))
            except:
                pass
            client_socket.close()
            return

    try:
        # 接收用户名
        username_data = client_socket.recv(1024).decode('utf-8')
        username = json.loads(username_data)["username"]

        with lock:
            # 检查用户名黑名单
            if username in banned_users:
                resp = json.dumps({
                    "type": "error",
                    "msg": "你已被拉黑，无法登录！"
                }, ensure_ascii=False)
                client_socket.send(resp.encode('utf-8'))
                client_socket.close()
                return

            # 检查用户名是否已存在
            if username in clients:
                resp = json.dumps({"type": "error", "msg": "用户名已存在！"}, ensure_ascii=False)
                client_socket.send(resp.encode('utf-8'))
                client_socket.close()
                return

            clients[username] = (client_socket, addr)

        broadcast_message("系统", f"{username} 已上线！当前在线人数：{len(clients)}")
        log_queue.put(f"[{get_current_time()}] {username} ({addr}) 已连接，当前在线：{len(clients)}")

        while server_running:
            try:
                msg = client_socket.recv(1024).decode('utf-8')
            except:
                break
            if not msg:
                break

            msg_data = json.loads(msg)
            if msg_data["type"] == "message":
                content = msg_data["content"]
                now = time.time()

                # 简单的速率限制
                if now - last_msg_time <= 1.0:
                    char_count += 1
                else:
                    char_count += 1
                    last_msg_time = now

                # 检查是否是管理员命令
                is_admin = False
                with lock:
                    is_admin = username in admins

                if is_admin:
                    # 处理踢人命令
                    if content.startswith("kick "):
                        parts = content.split()
                        if len(parts) == 2:
                            target = parts[1]
                            kick_user(target)
                        else:
                            send_system_message(username, "格式错误，请使用: kick 用户名")
                    # 处理拉黑命令
                    elif content.startswith("ban "):
                        parts = content.split()
                        if len(parts) == 2:
                            target = parts[1]
                            ban_user(target)
                        else:
                            send_system_message(username, "格式错误，请使用: ban 用户名")
                    else:
                        # 普通消息
                        broadcast_message(username, content)
                else:
                    # 普通用户消息
                    broadcast_message(username, content)

    except Exception as e:
        log_queue.put(f"[{get_current_time()}] 处理客户端 {addr} 时出错：{e}")
    finally:
        # 清理断开连接的客户端
        if username and username in clients:
            with lock:
                del clients[username]
            broadcast_message("系统", f"{username} 已下线！当前在线人数：{len(clients)}")
            log_queue.put(f"[{get_current_time()}] {username} ({addr}) 已断开，当前在线：{len(clients)}")
        client_socket.close()


def start_server():
    global server_socket, server_running
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    log_queue.put(f"[{get_current_time()}] 服务器已启动，监听地址：{HOST}:{PORT}")

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
