"""使用Chrome CDP模式捕获小红书直播网络请求"""
import json
import time
import re

try:
    from selenium import webdriver
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium未安装，正在尝试安装...")
    import subprocess
    subprocess.run(['d:\\xhs_stream_capturer\\venv\\Scripts\\pip', 'install', 'selenium'], check=True)
    from selenium import webdriver
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    from selenium.webdriver.chrome.options import Options

def capture_network_requests(url, wait_time=15):
    """
    使用Chrome CDP捕获网络请求
    
    Args:
        url: 目标URL
        wait_time: 等待页面加载的时间（秒）
    """
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    
    # 配置Chrome选项
    options = Options()
    options.add_argument('--headless')  # 无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    # 设置用户代理
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # 启用性能日志以捕获网络请求 (Selenium 4.x 方式)
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    # 创建WebDriver
    driver = webdriver.Chrome(options=options)
    
    stream_urls = []
    
    try:
        print(f"正在访问: {url}")
        driver.get(url)
        
        print(f"等待页面加载 ({wait_time}秒)...")
        time.sleep(wait_time)
        
        # 获取性能日志
        logs = driver.get_log('performance')
        
        print(f"\n捕获到 {len(logs)} 条网络日志")
        
        # 分析日志
        for entry in logs:
            try:
                log = json.loads(entry['message'])
                message = log.get('message', {})
                method = message.get('method', '')
                
                # 关注网络请求
                if method == 'Network.requestWillBeSent':
                    request = message.get('params', {}).get('request', {})
                    request_url = request.get('url', '')
                    
                    # 查找包含流媒体的URL
                    if any(keyword in request_url.lower() for keyword in ['.flv', '.m3u8', 'stream', 'live', 'hls', 'rtmp']):
                        stream_urls.append({
                            'url': request_url,
                            'method': request.get('method', 'GET'),
                            'type': 'stream'
                        })
                        print(f"\n找到流媒体URL: {request_url[:150]}")
                    
                    # 查找直播相关的API请求
                    if any(keyword in request_url.lower() for keyword in ['livestream', 'live/api', 'api/live']):
                        stream_urls.append({
                            'url': request_url,
                            'method': request.get('method', 'GET'),
                            'type': 'api'
                        })
                        print(f"\n找到直播API: {request_url[:150]}")
                        
                # 关注网络响应
                elif method == 'Network.responseReceived':
                    response = message.get('params', {}).get('response', {})
                    response_url = response.get('url', '')
                    content_type = response.get('mimeType', '')
                    
                    # 检查响应类型
                    if any(ct in content_type.lower() for ct in ['video', 'stream', 'x-mpegurl', 'x-flv']):
                        stream_urls.append({
                            'url': response_url,
                            'content_type': content_type,
                            'type': 'media_response'
                        })
                        print(f"\n找到媒体响应: {response_url[:150]} ({content_type})")
                        
            except json.JSONDecodeError:
                continue
            except Exception as e:
                continue
        
        # 尝试从页面源代码中提取
        page_source = driver.page_source
        print(f"\n页面源代码长度: {len(page_source)}")
        
        # 搜索可能的流地址模式
        patterns = [
            r'https?://[^\s"\'<>]+\.flv[^\s"\'<>]*',
            r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*',
            r'"(https?://[^"\']+stream[^"\']+)"',
            r'"(https?://[^"\']+live[^"\']+)"',
        ]
        
        print("\n从页面源代码搜索流地址...")
        for pattern in patterns:
            matches = re.findall(pattern, page_source, re.IGNORECASE)
            for match in matches[:5]:
                url_match = match if isinstance(match, str) else match
                if url_match not in [s['url'] for s in stream_urls]:
                    stream_urls.append({
                        'url': url_match,
                        'type': 'page_source'
                    })
                    print(f"从页面找到: {url_match[:150]}")
        
    finally:
        driver.quit()
    
    return stream_urls


if __name__ == "__main__":
    # 测试URL - 用户提供的正在直播的链接
    #test_url = "http://xhslink.com/m/3NvDA7pR66X"
    test_url = "https://www.xiaohongshu.com/livestream/dynpathidGh8RZU/570200639344214097?timestamp=1774356234480&share_source=share_link&share_source_id=&source=share_out_of_app&host_id=5d00d995000000001200d086"
    
    print("=" * 60)
    print("小红书直播网络请求捕获工具")
    print("=" * 60)
    
    stream_urls = capture_network_requests(test_url, wait_time=20)
    
    print("\n" + "=" * 60)
    print(f"共找到 {len(stream_urls)} 个相关URL:")
    print("=" * 60)
    
    for i, item in enumerate(stream_urls, 1):
        print(f"\n{i}. [{item.get('type', 'unknown')}] {item.get('url', '')[:200]}")
    
    # 保存结果
    with open('d:/xhs_stream_capturer/network_capture_result.json', 'w', encoding='utf-8') as f:
        json.dump(stream_urls, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: d:/xhs_stream_capturer/network_capture_result.json")