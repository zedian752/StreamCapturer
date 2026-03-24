"""
小红书直播链接转换器
支持短链接转长链接，并获取直播流地址
"""
import re
import json
import time
import requests
import subprocess
import os
from typing import Optional, Tuple


class LinkConverter:
    """小红书直播链接转换器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.chrome_process = None
        self.ws = None
    
    def convert_short_url(self, short_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        将短链接转换为长链接并提取房间ID
        
        Args:
            short_url: 小红书短链接 (如 http://xhslink.com/m/xxxxx)
            
        Returns:
            (长链接, 房间ID) 或 (None, None)
        """
        try:
            # 如果已经是长链接
            if 'xiaohongshu.com/livestream' in short_url:
                room_id = self._extract_room_id(short_url)
                return short_url, room_id
            
            # 短链接重定向
            response = self.session.get(short_url, allow_redirects=True, timeout=10)
            final_url = response.url
            
            room_id = self._extract_room_id(final_url)
            return final_url, room_id
            
        except Exception as e:
            print(f"转换短链接失败: {e}")
            return None, None
    
    def _extract_room_id(self, url: str) -> Optional[str]:
        """从URL中提取房间ID"""
        # 匹配模式: /livestream/dynpathXXX/ROOM_ID
        match = re.search(r'/livestream/[^/]+/(\d+)', url)
        if match:
            return match.group(1)
        return None
    
    def get_stream_url_via_cdp(self, room_id: str, wait_time: int = 15) -> Optional[str]:
        """
        使用Chrome CDP获取直播流地址
        
        Args:
            room_id: 直播间ID
            wait_time: 等待页面加载时间（秒）
            
        Returns:
            直播流URL或None
        """
        try:
            import websocket
        except ImportError:
            print("请先安装websocket-client: pip install websocket-client")
            return None
        
        port = 9223  # 使用不同端口避免冲突
        
        try:
            # 启动Chrome
            chrome_exe = self._find_chrome()
            if not chrome_exe:
                print("未找到Chrome浏览器")
                return None
            
            user_data_dir = r"d:\xhs_stream_capturer\chrome_temp_profile"
            os.makedirs(user_data_dir, exist_ok=True)
            
            cmd = [
                chrome_exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--headless",
                "--disable-gpu",
                "--window-size=1920,1080",
                "--remote-allow-origins=*",
            ]
            
            print(f"启动Chrome (端口 {port})...")
            self.chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            
            # 获取WebSocket URL
            try:
                response = requests.get(f"http://localhost:{port}/json", timeout=5)
                tabs = response.json()
                ws_url = None
                for tab in tabs:
                    if 'webSocketDebuggerUrl' in tab:
                        ws_url = tab['webSocketDebuggerUrl']
                        break
                
                if not ws_url:
                    print("无法获取WebSocket URL")
                    return None
            except Exception as e:
                print(f"连接Chrome失败: {e}")
                return None
            
            # 连接WebSocket
            self.ws = websocket.create_connection(ws_url)
            
            # 启用网络监控
            self._send_command("Network.enable")
            self._send_command("Page.enable")
            
            # 构造直播页面URL
            live_url = f"https://www.xiaohongshu.com/livestream/room/{room_id}"
            print(f"访问直播间: {live_url}")
            self._send_command("Page.navigate", {"url": live_url})
            
            # 监听网络请求
            print(f"等待捕获直播流 ({wait_time}秒)...")
            self.ws.settimeout(1)
            start_time = time.time()
            stream_url = None
            
            while time.time() - start_time < wait_time:
                try:
                    result = self.ws.recv()
                    if result:
                        data = json.loads(result)
                        method = data.get("method", "")
                        
                        if method == "Network.requestWillBeSent":
                            request = data.get("params", {}).get("request", {})
                            request_url = request.get("url", "")
                            
                            # 检查是否是直播流URL
                            if 'live-source-play.xhscdn.com' in request_url and '.flv' in request_url:
                                print(f"找到直播流: {request_url}")
                                stream_url = request_url
                                break
                                
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception:
                    continue
            
            return stream_url
            
        except Exception as e:
            print(f"CDP捕获失败: {e}")
            return None
        finally:
            self._cleanup()
    
    def _find_chrome(self) -> Optional[str]:
        """查找Chrome浏览器路径"""
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _send_command(self, method: str, params: dict = None):
        """发送CDP命令"""
        cmd = {"id": 1, "method": method}
        if params:
            cmd["params"] = params
        self.ws.send(json.dumps(cmd))
        return json.loads(self.ws.recv())
    
    def _cleanup(self):
        """清理资源"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        if self.chrome_process:
            try:
                self.chrome_process.terminate()
            except:
                pass
    
    def get_stream_url_simple(self, room_id: str) -> Optional[str]:
        """
        简单方式获取直播流URL（基于已知格式构造）
        注意：此方法可能需要更新签名参数
        
        Args:
            room_id: 直播间ID
            
        Returns:
            直播流URL或None
        """
        # 基于捕获到的URL格式构造
        # 格式: https://live-source-play.xhscdn.com/live/{room_id}_orig.flv
        # 注意：实际URL可能需要额外的签名参数
        base_url = f"https://live-source-play.xhscdn.com/live/{room_id}_orig.flv"
        return base_url


def test_converter():
    """测试链接转换器"""
    converter = LinkConverter()
    
    # 测试短链接
    short_url = "http://xhslink.com/m/AZKB2inRqtk"
    print(f"\n测试短链接: {short_url}")
    long_url, room_id = converter.convert_short_url(short_url)
    print(f"长链接: {long_url}")
    print(f"房间ID: {room_id}")
    
    # 测试直接获取流URL
    if room_id:
        print(f"\n获取直播流URL (房间ID: {room_id})...")
        stream_url = converter.get_stream_url_simple(room_id)
        print(f"直播流URL: {stream_url}")


if __name__ == "__main__":
    test_converter()