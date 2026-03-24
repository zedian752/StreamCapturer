"""使用Chrome CDP协议捕获小红书直播网络请求"""
import json
import time
import re
import requests
import subprocess
import os

def start_chrome_with_debugging():
    """启动带有远程调试的Chrome浏览器"""
    # 常见的Chrome路径
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    
    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break
    
    if not chrome_exe:
        print("未找到Chrome浏览器，请确保已安装Chrome")
        return None
    
    # 创建临时用户数据目录
    user_data_dir = r"d:\xhs_stream_capturer\chrome_temp_profile"
    os.makedirs(user_data_dir, exist_ok=True)
    
    # 启动Chrome with remote debugging
    port = 9222
    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1920,1080",
        "--remote-allow-origins=*",
    ]
    
    print(f"启动Chrome: {chrome_exe}")
    print(f"调试端口: {port}")
    
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 等待Chrome启动
    time.sleep(3)
    
    return port, process

def get_websocket_url(port):
    """获取WebSocket调试URL"""
    try:
        response = requests.get(f"http://localhost:{port}/json")
        tabs = response.json()
        for tab in tabs:
            if 'webSocketDebuggerUrl' in tab:
                return tab['webSocketDebuggerUrl']
    except Exception as e:
        print(f"获取WebSocket URL失败: {e}")
    return None

def capture_with_cdp(url, wait_time=20):
    """使用CDP协议捕获网络请求"""
    import websocket
    
    # 启动Chrome
    result = start_chrome_with_debugging()
    if not result:
        return []
    
    port, chrome_process = result
    
    stream_urls = []
    ws_url = None
    
    try:
        # 获取WebSocket URL
        ws_url = get_websocket_url(port)
        if not ws_url:
            print("无法获取WebSocket调试URL")
            return []
        
        print(f"WebSocket URL: {ws_url}")
        
        # 连接到Chrome
        ws = websocket.create_connection(ws_url)
        
        # 启用网络监控
        def send_command(method, params=None):
            cmd = {"id": 1, "method": method}
            if params:
                cmd["params"] = params
            ws.send(json.dumps(cmd))
            return json.loads(ws.recv())
        
        print("启用网络监控...")
        send_command("Network.enable")
        send_command("Page.enable")
        
        # 导航到页面
        print(f"导航到: {url}")
        send_command("Page.navigate", {"url": url})
        
        # 监听网络事件
        print(f"等待页面加载 ({wait_time}秒)...")
        start_time = time.time()
        request_urls = {}
        
        ws.settimeout(1)  # 设置超时以便可以检查时间
        
        while time.time() - start_time < wait_time:
            try:
                result = ws.recv()
                if result:
                    data = json.loads(result)
                    method = data.get("method", "")
                    
                    if method == "Network.requestWillBeSent":
                        request = data.get("params", {}).get("request", {})
                        request_url = request.get("url", "")
                        request_id = data.get("params", {}).get("requestId", "")
                        request_urls[request_id] = request_url
                        
                        # 保存所有请求用于分析
                        if request_url and request_url not in [s.get('url') for s in stream_urls]:
                            # 检查所有有意义的URL
                            url_lower = request_url.lower()
                            is_interesting = any(kw in url_lower for kw in [
                                '.flv', '.m3u8', 'stream', 'hls', 'rtmp', 'live',
                                'video', 'media', 'play', 'broadcast', 'room',
                                'xhslink', 'xiaohongshu', 'api'
                            ])
                            if is_interesting:
                                stream_urls.append({
                                    'url': request_url,
                                    'type': 'request'
                                })
                                print(f"\n[请求] {request_url[:150]}")
                    
                    elif method == "Network.responseReceived":
                        response = data.get("params", {}).get("response", {})
                        content_type = response.get("mimeType", "")
                        request_id = data.get("params", {}).get("requestId", "")
                        response_url = response.get("url", "")
                        
                        # 捕获直播API响应
                        if 'live-room.xiaohongshu.com' in response_url or 'current_room_info' in response_url:
                            print(f"\n[直播API响应] {response_url[:150]}")
                            # 获取响应体
                            try:
                                ws.send(json.dumps({"id": 999, "method": "Network.getResponseBody", "params": {"requestId": request_id}}))
                                resp_result = ws.recv()
                                resp_data = json.loads(resp_result)
                                if 'result' in resp_data and 'body' in resp_data['result']:
                                    body = resp_data['result']['body']
                                    print(f"  响应内容: {body[:500]}...")
                                    # 保存响应
                                    with open('d:/xhs_stream_capturer/live_api_response.json', 'w', encoding='utf-8') as f:
                                        f.write(body)
                                    print(f"  已保存到 live_api_response.json")
                            except Exception as e:
                                print(f"  获取响应体失败: {e}")
                        
                        if any(ct in content_type.lower() for ct in ['video', 'stream', 'x-mpegurl', 'x-flv']):
                            orig_url = request_urls.get(request_id, response.get("url", ""))
                            if orig_url not in [s['url'] for s in stream_urls]:
                                stream_urls.append({
                                    'url': orig_url,
                                    'type': 'media_response',
                                    'content_type': content_type
                                })
                                print(f"\n[媒体响应] {orig_url[:150]} ({content_type})")
                                
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                continue
        
        ws.close()
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭Chrome
        if chrome_process:
            print("\n关闭Chrome...")
            chrome_process.terminate()
    
    return stream_urls


if __name__ == "__main__":
    # 安装websocket-client
    try:
        import websocket
    except ImportError:
        print("安装websocket-client...")
        import subprocess
        subprocess.run(['d:\\xhs_stream_capturer\\venv\\Scripts\\pip', 'install', 'websocket-client'], check=True)
        import websocket
    
    test_url = "https://www.xiaohongshu.com/livestream/dynpathhq6MrcXn/570200729166651969?timestamp=1774357252410&share_source=share_link&share_source_id=&source=share_out_of_app&host_id=661282a5000000000d02655b"
    
    print("=" * 60)
    print("小红书直播网络请求捕获工具 (CDP模式)")
    print("=" * 60)
    
    stream_urls = capture_with_cdp(test_url, wait_time=25)
    
    print("\n" + "=" * 60)
    print(f"共找到 {len(stream_urls)} 个相关URL:")
    print("=" * 60)
    
    for i, item in enumerate(stream_urls, 1):
        print(f"\n{i}. [{item.get('type', 'unknown')}] {item.get('url', '')[:200]}")
    
    # 保存结果
    with open('d:/xhs_stream_capturer/network_capture_result.json', 'w', encoding='utf-8') as f:
        json.dump(stream_urls, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: d:/xhs_stream_capturer/network_capture_result.json")