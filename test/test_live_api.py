"""测试小红书直播API获取流地址"""
import requests
import json
import re

def get_live_stream_url(room_id):
    """获取直播流地址"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Origin': 'https://www.xiaohongshu.com',
        'Referer': f'https://www.xiaohongshu.com/livestream/',
    })
    
    # 获取房间信息API
    room_info_url = f"https://live-room.xiaohongshu.com/api/sns/red/live/web/v1/room/current_room_info?room_id={room_id}&request_user_id=&source=web_live&client_type=1"
    
    print(f"请求房间信息: {room_info_url}")
    
    try:
        response = session.get(room_info_url)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # 尝试提取流地址
            if 'data' in data:
                room_data = data['data']
                
                # 查找可能的流地址字段
                stream_fields = ['stream', 'flv', 'hls', 'playUrl', 'streamUrl', 'liveStream', 'url']
                for field in stream_fields:
                    if field in str(room_data).lower():
                        print(f"\n找到字段包含 '{field}':")
                
                # 递归查找所有URL
                def find_urls(obj, path=''):
                    urls = []
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            new_path = f"{path}.{k}" if path else k
                            if isinstance(v, str) and ('http' in v or '.flv' in v or '.m3u8' in v):
                                urls.append((new_path, v))
                            urls.extend(find_urls(v, new_path))
                    elif isinstance(obj, list):
                        for i, v in enumerate(obj):
                            urls.extend(find_urls(v, f"{path}[{i}]"))
                    return urls
                
                urls = find_urls(room_data)
                if urls:
                    print("\n找到的URL:")
                    for path, url in urls:
                        print(f"  {path}: {url[:150]}")
                
                return data
        else:
            print(f"请求失败: {response.text}")
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    
    return None

if __name__ == "__main__":
    # 从用户提供的URL中提取房间ID
    room_id = "570200638150249802"
    
    print("=" * 60)
    print("小红书直播API测试")
    print("=" * 60)
    
    result = get_live_stream_url(room_id)