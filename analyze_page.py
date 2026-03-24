"""分析小红书直播页面，提取流地址"""
import re
import json

# 读取页面内容
with open('d:/xhs_stream_capturer/page_content.html', 'r', encoding='utf-8') as f:
    html = f.read()

print(f'页面长度: {len(html)}')

# 搜索可能包含流地址的模式
patterns = [
    (r'"streamUrl":"([^"]+)"', 'streamUrl'),
    (r'"flvUrl":"([^"]+)"', 'flvUrl'),
    (r'"hlsUrl":"([^"]+)"', 'hlsUrl'),
    (r'"flv":"([^"]+)"', 'flv'),
    (r'"hls":"([^"]+)"', 'hls'),
    (r'"playUrl":"([^"]+)"', 'playUrl'),
    (r'https?://[^\s"\'<>]+\.flv[^\s"\'<>]*', 'flv_raw'),
    (r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', 'm3u8_raw'),
]

print('\n=== 搜索流地址 ===')
for pattern, name in patterns:
    matches = re.findall(pattern, html)
    if matches:
        print(f'\n{name} 找到 {len(matches)} 个匹配:')
        for m in matches[:3]:
            print(f'  {m[:150]}...' if len(m) > 150 else f'  {m}')

# 搜索 __INITIAL_STATE__
state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;', html, re.DOTALL)
if state_match:
    print('\n__INITIAL_STATE__ 找到!')
    state_str = state_match.group(1)
    print(f'内容长度: {len(state_str)}')
    # 尝试解析JSON
    try:
        data = json.loads(state_str)
        print('JSON解析成功!')
        # 查找直播相关的key
        def find_keys(obj, prefix=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if 'live' in k.lower() or 'stream' in k.lower():
                        print(f'  {prefix}{k}: {str(v)[:100]}...')
                    find_keys(v, f'{prefix}{k}.')
        find_keys(data)
    except Exception as e:
        print(f'JSON解析失败: {e}')
        print(f'内容预览: {state_str[:500]}...')

# 搜索 room_id
room_matches = re.findall(r'"roomId":"?(\d+)"?', html)
if room_matches:
    print(f'\nroomId 找到: {set(room_matches)}')

# 搜索所有包含 live 或 stream 的 JSON key
live_keys = re.findall(r'"(\w*[Ll]ive\w*)"\s*:\s*"([^"]*)"', html)
stream_keys = re.findall(r'"(\w*[Ss]tream\w*)"\s*:\s*"([^"]*)"', html)

if live_keys:
    print(f'\n包含 live 的key:')
    for k, v in live_keys[:10]:
        print(f'  {k}: {v[:100]}...' if len(v) > 100 else f'  {k}: {v}')

if stream_keys:
    print(f'\n包含 stream 的key:')
    for k, v in stream_keys[:10]:
        print(f'  {k}: {v[:100]}...' if len(v) > 100 else f'  {k}: {v}')

# 搜索更多关键词
print('\n=== 搜索其他关键词 ===')

# 搜索 hls, flv, m3u8, rtmp
media_patterns = [
    (r'"(hls[^"]*)"[^:]*:\s*"([^"]+)"', 'hls keys'),
    (r'"(flv[^"]*)"[^:]*:\s*"([^"]+)"', 'flv keys'),
    (r'"(rtmp[^"]*)"[^:]*:\s*"([^"]+)"', 'rtmp keys'),
    (r'"(playUrl[^"]*)"[^:]*:\s*"([^"]+)"', 'playUrl keys'),
    (r'"(url[^"]*)"[^:]*:\s*"(https?[^"]+)"', 'url keys with http'),
]

for pattern, name in media_patterns:
    matches = re.findall(pattern, html, re.IGNORECASE)
    if matches:
        print(f'\n{name} 找到 {len(matches)} 个:')
        for k, v in matches[:5]:
            print(f'  {k}: {v[:150]}...' if len(v) > 150 else f'  {k}: {v}')

# 搜索API端点
api_patterns = [
    (r'/api/livestream/[^"\'>\s]+', 'livestream API'),
    (r'/livestream/api/[^"\'>\s]+', 'livestream API 2'),
    (r'api\.[^"\'>\s]*live[^"\'>\s]*', 'live API domain'),
]

for pattern, name in api_patterns:
    matches = re.findall(pattern, html)
    if matches:
        print(f'\n{name} 找到: {set(matches)}')

# 搜索房间ID的更精确模式
room_id_patterns = [
    r'"id"\s*:\s*"?(570\d+)"?',
    r'"roomId"\s*:\s*"?(570\d+)"?',
    r'/livestream/[^/]+/(\d+)',
]

print('\n=== 房间ID搜索 ===')
for pattern in room_id_patterns:
    matches = re.findall(pattern, html)
    if matches:
        print(f'找到房间ID: {set(matches)}')

# 搜索JSON中的关键信息
print('\n=== 搜索JSON块 ===')
# 找到所有script标签中的JSON
script_jsons = re.findall(r'<script[^>]*>\s*(\{[^<]+\})\s*</script>', html)
for i, sj in enumerate(script_jsons[:5]):
    if 'live' in sj.lower() or 'stream' in sj.lower():
        print(f'\nScript JSON {i} (包含 live/stream):')
        print(sj[:500])
