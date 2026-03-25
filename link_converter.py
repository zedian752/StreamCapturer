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
        self._last_long_url = None  # 保存最后一次转换的长链接
    
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
    
    def get_stream_url(self, room_id: str) -> Optional[str]:
        """
        获取直播流URL
        
        通过调用小红书直播API获取流地址
        
        Args:
            room_id: 直播间ID
            
        Returns:
            直播流URL或None
        """
        # 方法1: 尝试调用直播API获取流地址
        stream_url = self._get_stream_url_from_api(room_id)
        if stream_url:
            return stream_url
        
        # 方法2: 基于已知格式构造流地址
        # 格式: https://live-source-play.xhscdn.com/live/{room_id}_hcv520.flv
        # 注意：hcv520 是观察到的固定后缀
        return self._build_stream_url(room_id)
    
    def _get_stream_url_from_api(self, room_id: str) -> Optional[str]:
        """
        通过API获取直播流地址
        
        Args:
            room_id: 直播间ID
            
        Returns:
            流URL或None
        """
        try:
            # 小红书直播间信息API
            api_url = f"https://live-room.xiaohongshu.com/api/sns/red/live/web/v1/room/current_room_info"
            params = {
                'room_id': room_id,
                'source': 'web_live',
                'client_type': 1
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'https://www.xiaohongshu.com/livestream/',
                'Accept': 'application/json, text/plain, */*',
            }
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # 解析返回数据获取流地址
                if data.get('success'):
                    room_info = data.get('data', {})
                    # 尝试从不同字段获取流地址
                    stream_info = room_info.get('stream', {}) or room_info.get('live_stream', {})
                    
                    # 可能的字段名
                    for field in ['flv_pull_url', 'flv_url', 'stream_url', 'hls_pull_url']:
                        if stream_info.get(field):
                            return stream_info[field]
                    
                    # 嵌套结构
                    flv_urls = stream_info.get('flv', {})
                    if flv_urls:
                        # 获取第一个可用的FLV地址
                        for quality, url in flv_urls.items():
                            if url:
                                return url
                    
                    # 打印响应结构便于调试
                    print(f"API响应: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            
            return None
            
        except Exception as e:
            print(f"API获取流地址失败: {e}")
            return None
    
    def _build_stream_url(self, room_id: str) -> str:
        """
        根据已知格式构造流地址
        
        观察到的格式:
        https://live-source-play.xhscdn.com/live/{room_id}_hcv520.flv?userId=xxx
        
        Args:
            room_id: 直播间ID
            
        Returns:
            流URL
        """
        # 基于捕获到的URL格式构造
        base_url = f"https://live-source-play.xhscdn.com/live/{room_id}_hcv520.flv"
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