"""
直播流音频截取测试脚本
从直播流截取指定时长的音频并保存为文件，用于后续测试
"""

import os
import sys
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===========================================
# 在这里填入直播流短链接
# ===========================================
SHORT_LINK = "http://xhslink.com/m/7Fg5NhNGZqd"  # 例如: "http://xhslink.com/m/xxxxx"
# ===========================================

# 录制时长（秒）
DURATION = 30

# 输出文件路径
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_audio")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "live_audio_30s.wav")


def capture_audio(short_link: str, duration: int, output_file: str) -> bool:
    """
    从直播流截取音频并保存
    
    Args:
        short_link: 小红书直播短链接
        duration: 录制时长（秒）
        output_file: 输出文件路径
        
    Returns:
        是否成功
    """
    from link_converter import LinkConverter
    from stream_capturer import StreamCapturer
    
    print("=" * 60)
    print("直播流音频截取")
    print("=" * 60)
    
    if not short_link:
        print("错误: 请先设置 SHORT_LINK 变量")
        return False
    
    # 创建输出目录
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 步骤1: 转换链接获取直播流地址
    print(f"正在解析链接: {short_link}")
    converter = LinkConverter()
    long_url, room_id = converter.convert_short_url(short_link)
    
    if not room_id:
        print("错误: 无法从链接中提取房间ID")
        return False
    
    print(f"房间ID: {room_id}")
    
    # 获取直播流URL
    stream_url = converter.get_stream_url(room_id)
    if not stream_url:
        print("错误: 无法获取直播流地址，可能直播已结束")
        return False
    
    print(f"直播流地址: {stream_url[:80]}...")
    
    # 步骤2: 录制音频
    print(f"\n开始录制 {duration} 秒音频...")
    print(f"输出文件: {output_file}")
    
    capturer = StreamCapturer(
        sample_rate=16000,
        channels=1,
        buffer_size=5,
    )
    
    # 直接保存到文件
    success = capturer.save_audio_to_file(output_file, duration)
    
    if success:
        file_size = os.path.getsize(output_file)
        print(f"\n录制完成!")
        print(f"文件大小: {file_size / 1024:.1f} KB")
        print(f"文件路径: {output_file}")
        return True
    else:
        print("录制失败")
        return False


def capture_audio_manual(short_link: str, duration: int, output_file: str) -> bool:
    """
    手动方式录制音频（更可控）
    
    Args:
        short_link: 小红书直播短链接
        duration: 录制时长（秒）
        output_file: 输出文件路径
        
    Returns:
        是否成功
    """
    import subprocess
    from link_converter import LinkConverter
    
    print("=" * 60)
    print("直播流音频截取 (手动模式)")
    print("=" * 60)
    
    if not short_link:
        print("错误: 请先设置 SHORT_LINK 变量")
        return False
    
    # 创建输出目录
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 获取直播流地址
    print(f"正在解析链接: {short_link}")
    converter = LinkConverter()
    long_url, room_id = converter.convert_short_url(short_link)
    
    if not room_id:
        print("错误: 无法从链接中提取房间ID")
        return False
    
    stream_url = converter.get_stream_url(room_id)
    if not stream_url:
        print("错误: 无法获取直播流地址，可能直播已结束")
        return False
    
    print(f"直播流地址: {stream_url[:80]}...")
    
    # 查找ffmpeg
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ffmpeg_path = os.path.join(project_dir, 'ffmpeg.exe')
    if not os.path.exists(ffmpeg_path):
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
    
    if not ffmpeg_path:
        print("错误: 找不到FFmpeg")
        return False
    
    # 构建FFmpeg命令
    ffmpeg_cmd = [
        ffmpeg_path,
        '-i', stream_url,
        '-vn',  # 不处理视频
        '-acodec', 'pcm_s16le',  # 16位PCM
        '-ar', '16000',  # 采样率
        '-ac', '1',  # 单声道
        '-t', str(duration),  # 时长
        '-y',  # 覆盖
        output_file
    ]
    
    print(f"\n开始录制 {duration} 秒音频...")
    print(f"输出文件: {output_file}")
    print("请等待...")
    
    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待完成
        stdout, stderr = process.communicate(timeout=duration + 30)
        
        if process.returncode == 0:
            file_size = os.path.getsize(output_file)
            print(f"\n录制完成!")
            print(f"文件大小: {file_size / 1024:.1f} KB")
            print(f"文件路径: {output_file}")
            return True
        else:
            print(f"录制失败: {stderr.decode('utf-8', errors='ignore')[-500:]}")
            return False
            
    except subprocess.TimeoutExpired:
        process.kill()
        print("录制超时")
        return False
    except Exception as e:
        print(f"录制错误: {e}")
        return False


if __name__ == "__main__":
    # 使用手动模式（更稳定）
    capture_audio_manual(SHORT_LINK, DURATION, OUTPUT_FILE)