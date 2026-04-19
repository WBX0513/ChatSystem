import socket
import threading
import json
from datetime import datetime

# 服务器配置
HOST = '0.0.0.0'  # 监听所有可用的网络接口
PORT = 9999       # 监听端口
clients = {}      # 存储客户端连接: {用户名: (socket, 地址)}
lock = threading.Lock()  # 线程锁，保证多线程安全

def get_current_time():
    """获取格式化的当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def broadcast_message(sender, message):
    """广播消息给所有在线用户"""
    with lock:
        # 构造消息体
        msg_data = {
            "type": "message",
            "sender": sender,
            "content": message,
            "time": get_current_time()
        }
        msg_json = json.dumps(msg_data, ensure_ascii=False)
        
        # 遍历所有客户端并发送消息
        for username, (client_socket, addr) in clients.items():
            if username != sender:  # 不回发给发送者自己
                try:
                    client_socket.send(msg_json.encode('utf-8'))
                except:
                    # 发送失败则移除该客户端
                    print(f"[{get_current_time()}] 客户端 {username} 连接异常，已移除")
                    del clients[username]

def handle_client(client_socket, addr):
    """处理单个客户端的消息循环"""
    username = None
    try:
        # 第一步：接收客户端的用户名
        username_data = client_socket.recv(1024).decode('utf-8')
        username = json.loads(username_data)["username"]
        
        with lock:
            # 检查用户名是否已存在
            if username in clients:
                resp = json.dumps({"type": "error", "msg": "用户名已存在！"}, ensure_ascii=False)
                client_socket.send(resp.encode('utf-8'))
                client_socket.close()
                return
            
            # 添加新客户端
            clients[username] = (client_socket, addr)
        
        # 通知所有人有新用户上线
        broadcast_message("系统", f"{username} 已上线！当前在线人数：{len(clients)}")
        print(f"[{get_current_time()}] {username} ({addr}) 已连接，当前在线：{len(clients)}")
        
        # 第二步：持续接收客户端消息
        while True:
            msg = client_socket.recv(1024).decode('utf-8')
            if not msg:  # 客户端断开连接
                break
            
            # 解析消息并广播
            msg_data = json.loads(msg)
            if msg_data["type"] == "message":
                broadcast_message(username, msg_data["content"])
    
    except Exception as e:
        print(f"[{get_current_time()}] 处理客户端 {addr} 时出错：{e}")
    finally:
        # 客户端断开连接后的清理工作
        if username and username in clients:
            with lock:
                del clients[username]
            broadcast_message("系统", f"{username} 已下线！当前在线人数：{len(clients)}")
            print(f"[{get_current_time()}] {username} ({addr}) 已断开，当前在线：{len(clients)}")
        client_socket.close()

def start_server():
    """启动服务器"""
    # 创建TCP套接字
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 设置端口复用，避免程序重启后端口被占用
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # 绑定地址和端口
    server_socket.bind((HOST, PORT))
    # 开始监听
    server_socket.listen(5)
    print(f"[{get_current_time()}] 服务器已启动，监听地址：{HOST}:{PORT}")
    
    try:
        # 持续接受新连接
        while True:
            client_socket, addr = server_socket.accept()
            # 为每个客户端创建独立线程处理
            client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
            client_thread.daemon = True  # 守护线程，主程序退出时自动结束
            client_thread.start()
    except KeyboardInterrupt:
        print(f"\n[{get_current_time()}] 服务器正在关闭...")
    finally:
        server_socket.close()
        print(f"[{get_current_time()}] 服务器已关闭")

if __name__ == "__main__":
    start_server()
