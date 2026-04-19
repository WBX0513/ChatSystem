import socket
import threading
import json
import time
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
from tkinter import font as tkfont
import queue
import os

# 服务器配置
HOST = '0.0.0.0'
PORT = 9999
clients = {}               # {用户名: (socket, 地址)}
banned_users = set()       # 被拉黑的用户名集合
banned_ips = set()         # 被封禁的IP地址集合
lock = threading.Lock()    # 保护 clients, banned_users, banned_ips
server_running = True
server_socket = None
log_queue = queue.Queue()  # 用于线程安全的日志输出
chat_records = []          # 全局聊天记录存储
log_records = []           # 全局日志记录存储

class ServerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("聊天服务器管理控制台")
        self.root.geometry("1000x750")
        
        # 设置样式
        self.root.configure(bg='#f0f0f0')
        
        # 创建主框架
        self.create_widgets()
        
        # 启动日志更新循环
        self.update_log()
        
        # 启动在线用户列表更新循环
        self.update_user_list()
        
        # 启动黑名单列表更新循环
        self.update_ban_list()
        
        # 启动IP封禁列表更新循环
        self.update_ipban_list()
        
        # 启动消息监测列表更新
        self.update_monitor_list()
        
        # 处理窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_widgets(self):
        # 顶部标题
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=50)
        title_frame.pack(fill=tk.X)
        title_label = tk.Label(title_frame, text="聊天服务器管理控制台", 
                               font=('Arial', 16, 'bold'), 
                               bg='#2c3e50', fg='white')
        title_label.pack(pady=10)
        
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
        
        # 左侧面板（日志+消息监测）
        left_panel = tk.Frame(main_panel, bg='#f0f0f0')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 日志区域
        log_frame = tk.LabelFrame(left_panel, text="服务器日志", 
                                  font=('Arial', 11, 'bold'),
                                  bg='#f0f0f0', padx=5, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 日志操作按钮
        log_btn_frame = tk.Frame(log_frame, bg='#f0f0f0')
        log_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(log_btn_frame, text="保存日志", bg='#27ae60', fg='white', 
                  command=self.save_log).pack(side=tk.LEFT, padx=2)
        tk.Button(log_btn_frame, text="清空日志", bg='#e74c3c', fg='white', 
                  command=self.clear_log).pack(side=tk.LEFT, padx=2)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, 
                                                   wrap=tk.WORD,
                                                   font=('Consolas', 10),
                                                   bg='white',
                                                   height=15)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # 消息监测区域
        monitor_frame = tk.LabelFrame(left_panel, text="消息监测", 
                                      font=('Arial', 11, 'bold'),
                                      bg='#f0f0f0', padx=5, pady=5)
        monitor_frame.pack(fill=tk.BOTH, expand=True)
        
        # 聊天记录操作按钮
        chat_btn_frame = tk.Frame(monitor_frame, bg='#f0f0f0')
        chat_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(chat_btn_frame, text="保存聊天记录", bg='#27ae60', fg='white', 
                  command=self.save_chat_records).pack(side=tk.LEFT, padx=2)
        tk.Button(chat_btn_frame, text="清空聊天记录", bg='#e74c3c', fg='white', 
                  command=self.clear_chat_records).pack(side=tk.LEFT, padx=2)
        
        self.monitor_area = scrolledtext.ScrolledText(monitor_frame, 
                                                      wrap=tk.WORD,
                                                      font=('Consolas', 10),
                                                      bg='white',
                                                      height=10)
        self.monitor_area.pack(fill=tk.BOTH, expand=True)
        
        # 右侧面板（管理区域）
        right_panel = tk.Frame(main_panel, bg='#f0f0f0', width=300)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        right_panel.pack_propagate(False)
        
        # 在线用户列表
        online_frame = tk.LabelFrame(right_panel, text="在线用户", 
                                     font=('Arial', 11, 'bold'),
                                     bg='#f0f0f0', padx=5, pady=5)
        online_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 在线用户列表和按钮
        online_list_frame = tk.Frame(online_frame, bg='#f0f0f0')
        online_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.user_listbox = tk.Listbox(online_list_frame, 
                                       font=('Arial', 10),
                                       bg='white',
                                       selectmode=tk.SINGLE,
                                       height=8)
        self.user_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        user_scrollbar = tk.Scrollbar(online_list_frame)
        user_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.user_listbox.config(yscrollcommand=user_scrollbar.set)
        user_scrollbar.config(command=self.user_listbox.yview)
        
        # 在线用户操作按钮
        online_btn_frame = tk.Frame(online_frame, bg='#f0f0f0')
        online_btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(online_btn_frame, text="踢出", 
                 bg='#e67e22', fg='white',
                 command=self.kick_selected_user).pack(side=tk.LEFT, padx=2)
        
        tk.Button(online_btn_frame, text="拉黑", 
                 bg='#e74c3c', fg='white',
                 command=self.ban_selected_user).pack(side=tk.LEFT, padx=2)
        
        # 黑名单列表
        ban_frame = tk.LabelFrame(right_panel, text="用户黑名单", 
                                  font=('Arial', 11, 'bold'),
                                  bg='#f0f0f0', padx=5, pady=5)
        ban_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        ban_list_frame = tk.Frame(ban_frame, bg='#f0f0f0')
        ban_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.ban_listbox = tk.Listbox(ban_list_frame, 
                                      font=('Arial', 10),
                                      bg='white',
                                      selectmode=tk.SINGLE,
                                      height=5)
        self.ban_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ban_scrollbar = tk.Scrollbar(ban_list_frame)
        ban_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.ban_listbox.config(yscrollcommand=ban_scrollbar.set)
        ban_scrollbar.config(command=self.ban_listbox.yview)
        
        # 黑名单操作按钮
        tk.Button(ban_frame, text="解除拉黑", 
                 bg='#27ae60', fg='white',
                 command=self.unban_selected_user).pack(fill=tk.X, pady=5)
        
        # IP封禁列表
        ipban_frame = tk.LabelFrame(right_panel, text="IP封禁列表", 
                                    font=('Arial', 11, 'bold'),
                                    bg='#f0f0f0', padx=5, pady=5)
        ipban_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        ipban_list_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        ipban_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.ipban_listbox = tk.Listbox(ipban_list_frame, 
                                        font=('Arial', 10),
                                        bg='white',
                                        selectmode=tk.SINGLE,
                                        height=5)
        self.ipban_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ipban_scrollbar = tk.Scrollbar(ipban_list_frame)
        ipban_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.ipban_listbox.config(yscrollcommand=ipban_scrollbar.set)
        ipban_scrollbar.config(command=self.ipban_listbox.yview)
        
        # IP封禁操作区域
        ipban_btn_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        ipban_btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(ipban_btn_frame, text="解除封禁", 
                 bg='#27ae60', fg='white',
                 command=self.unban_selected_ip).pack(side=tk.LEFT, padx=2)
        
        # IP封禁输入
        ip_input_frame = tk.Frame(ipban_frame, bg='#f0f0f0')
        ip_input_frame.pack(fill=tk.X)
        
        self.ip_entry = tk.Entry(ip_input_frame, font=('Arial', 10))
        self.ip_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        tk.Button(ip_input_frame, text="封禁IP", 
                 bg='#e74c3c', fg='white',
                 command=self.ban_ip).pack(side=tk.RIGHT)
        
        # 底部控制按钮
        bottom_frame = tk.Frame(self.root, bg='#f0f0f0')
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(bottom_frame, text="关闭服务器", 
                 bg='#c0392b', fg='white',
                 font=('Arial', 11, 'bold'),
                 command=self.on_closing).pack(side=tk.RIGHT)
        
        # 服务器状态标签
        self.status_label = tk.Label(bottom_frame, text="服务器运行中...", 
                                     font=('Arial', 10),
                                     bg='#f0f0f0', fg='#27ae60')
        self.status_label.pack(side=tk.LEFT)
    
    def log(self, message):
        """添加日志到队列和全局日志记录"""
        log_queue.put(message)
        log_records.append(message)
    
    def update_log(self):
        """更新日志显示"""
        try:
            while True:
                message = log_queue.get_nowait()
                self.log_area.insert(tk.END, message + '\n')
                self.log_area.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.update_log)
    
    def update_user_list(self):
        """更新在线用户列表"""
        with lock:
            current_users = list(clients.keys())
        
        self.user_listbox.delete(0, tk.END)
        for user in sorted(current_users):
            self.user_listbox.insert(tk.END, user)
        
        self.status_label.config(text=f"服务器运行中... 在线用户: {len(current_users)}")
        self.root.after(2000, self.update_user_list)
    
    def update_ban_list(self):
        """更新黑名单列表"""
        with lock:
            current_bans = list(banned_users)
        
        self.ban_listbox.delete(0, tk.END)
        for user in sorted(current_bans):
            self.ban_listbox.insert(tk.END, user)
        
        self.root.after(2000, self.update_ban_list)
    
    def update_ipban_list(self):
        """更新IP封禁列表"""
        with lock:
            current_ipbans = list(banned_ips)
        
        self.ipban_listbox.delete(0, tk.END)
        for ip in sorted(current_ipbans):
            self.ipban_listbox.insert(tk.END, ip)
        
        self.root.after(2000, self.update_ipban_list)
    
    def update_monitor_list(self):
        """更新消息监测列表"""
        self.monitor_area.config(state=tk.NORMAL)
        self.monitor_area.delete(1.0, tk.END)
        for record in chat_records:
            self.monitor_area.insert(tk.END, record + '\n')
        self.monitor_area.config(state=tk.DISABLED)
        self.monitor_area.see(tk.END)
        self.root.after(1000, self.update_monitor_list)
    
    def get_selected_user(self, listbox):
        """获取选中的用户名"""
        selection = listbox.curselection()
        if selection:
            return listbox.get(selection[0])
        return None
    
    def kick_selected_user(self):
        """踢出选中的用户"""
        username = self.get_selected_user(self.user_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要踢出用户 {username} 吗？"):
                kick_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")
    
    def ban_selected_user(self):
        """拉黑选中的用户"""
        username = self.get_selected_user(self.user_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要拉黑用户 {username} 吗？"):
                ban_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")
    
    def unban_selected_user(self):
        """解除选中的黑名单用户"""
        username = self.get_selected_user(self.ban_listbox)
        if username:
            if messagebox.askyesno("确认", f"确定要解除用户 {username} 的拉黑吗？"):
                unban_user(username)
        else:
            messagebox.showwarning("提示", "请先选择一个用户")
    
    def unban_selected_ip(self):
        """解除选中的IP封禁"""
        ip = self.get_selected_user(self.ipban_listbox)
        if ip:
            if messagebox.askyesno("确认", f"确定要解除IP {ip} 的封禁吗？"):
                unban_ip(ip)
        else:
            messagebox.showwarning("提示", "请先选择一个IP")
    
    def ban_ip(self):
        """封禁输入的IP"""
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
            notice_json = json.dumps(notice_data, ensure_ascii=False)
            # 广播公告给所有在线用户
            for username, (client_socket, addr) in list(clients.items()):
                try:
                    client_socket.send(notice_json.encode('utf-8'))
                except:
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
            self.monitor_area.config(state=tk.NORMAL)
            self.monitor_area.delete(1.0, tk.END)
            self.monitor_area.config(state=tk.DISABLED)
            self.log(f"[{get_current_time()}] 聊天记录已清空")
    
    def on_closing(self):
        """窗口关闭事件"""
        if messagebox.askyesno("确认", "确定要关闭服务器吗？"):
            self.log("正在关闭服务器...")
            shutdown_server()
            self.root.after(1000, self.root.destroy)
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def broadcast_message(sender, message):
    """广播消息给所有在线用户（除发送者外），并记录聊天记录"""
    with lock:
        msg_data = {
            "type": "message",
            "sender": sender,
            "content": message,
            "time": get_current_time()
        }
        msg_json = json.dumps(msg_data, ensure_ascii=False)
        # 记录聊天记录
        chat_record = f"[{msg_data['time']}] {sender}：{message}"
        chat_records.append(chat_record)
        # 广播消息
        for username, (client_socket, addr) in list(clients.items()):
            if username != sender:
                try:
                    client_socket.send(msg_json.encode('utf-8'))
                except:
                    log_queue.put(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                    del clients[username]

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

def list_bans():
    """列出所有被拉黑的用户"""
    with lock:
        if banned_users:
            log_queue.put(f"[{get_current_time()}] 当前用户黑名单: {', '.join(banned_users)}")
        else:
            log_queue.put(f"[{get_current_time()}] 用户黑名单为空")

def ban_ip(ip_address):
    """封禁IP地址：加入IP黑名单，若该IP有在线用户则全部踢出"""
    kicked_any = False
    with lock:
        banned_ips.add(ip_address)
        # 找出该IP的所有在线用户并断开连接
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

def list_banned_ips():
    """列出所有被封禁的IP"""
    with lock:
        if banned_ips:
            log_queue.put(f"[{get_current_time()}] 当前IP封禁列表: {', '.join(banned_ips)}")
        else:
            log_queue.put(f"[{get_current_time()}] IP封禁列表为空")

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
    """优化客户端消息处理，防止大量消息导致异常"""
    username = None
    last_msg_time = time.time()
    char_count = 0
    client_ip = addr[0]
    msg_buffer = ""  # 消息缓冲区，处理粘包
    
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
        # 接收用户名（处理粘包）
        while True:
            try:
                chunk = client_socket.recv(1024).decode('utf-8')
                if not chunk:
                    raise ConnectionResetError("客户端断开连接")
                msg_buffer += chunk
                # 尝试解析JSON
                username_data = json.loads(msg_buffer)
                msg_buffer = ""
                break
            except json.JSONDecodeError:
                # 未接收完整，继续接收
                continue
        
        username = username_data["username"]

        # 检查用户名黑名单
        with lock:
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

        # 限制消息接收速率，防止大量消息攻击
        msg_count = 0
        msg_time_window = time.time()
        
        while server_running:
            try:
                # 分段接收消息，处理粘包
                chunk = client_socket.recv(4096).decode('utf-8')  # 增大接收缓冲区
                if not chunk:
                    break
                msg_buffer += chunk
                
                # 按JSON边界分割消息（简单处理，实际可优化）
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
                            content = msg_data["content"]
                            
                            # 消息速率限制：10秒内最多接收20条消息
                            now = time.time()
                            if now - msg_time_window > 10:
                                msg_count = 0
                                msg_time_window = now
                            msg_count += 1
                            if msg_count > 20:
                                # 超出速率限制，暂时断开
                                limit_msg = json.dumps({
                                    "type": "system",
                                    "content": "消息发送速率过快，请稍后再试！",
                                    "time": get_current_time()
                                }, ensure_ascii=False)
                                client_socket.send(limit_msg.encode('utf-8'))
                                raise ConnectionResetError("消息速率超限")
                            
                            broadcast_message(username, content)
                    except json.JSONDecodeError:
                        # 未接收完整，继续缓冲
                        continue
                    
            except Exception as e:
                log_queue.put(f"[{get_current_time()}] 客户端 {username} 异常：{e}")
                break

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
                # 设置客户端套接字超时，防止阻塞
                client_socket.settimeout(300)
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
