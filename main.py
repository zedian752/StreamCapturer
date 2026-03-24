"""
小红书直播流捕获器 - 主程序
持续获取小红书直播流的音频信息，并通过语音识别转换为文字

使用方法:
    python main.py <短链接或直播间URL>
    
示例:
    python main.py http://xhslink.com/m/AZKB2inRqtk
    python main.py https://www.xiaohongshu.com/livestream/dynpathkeF6dmRm/570200151527099270
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import yaml

from link_converter import LinkConverter
from stream_capturer import StreamCapturer, StreamStatus, AudioChunk
from speech_recognizer import SpeechRecognizerManager, RecognitionResult


# 默认配置
DEFAULT_CONFIG = {
    'short_link': {
        'timeout': 10,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    },
    'stream': {
        'sample_rate': 16000,
        'channels': 1,
        'buffer_size': 5,
        'flv_timeout': 30,
        'reconnect_interval': 3,
        'max_reconnect_attempts': 10,
    },
    'speech_recognition': {
        'engine': 'whisper',
        'whisper': {
            'model': 'base',
            'language': 'zh',
            'device': 'cpu',
        }
    },
    'output': {
        'save_dir': './output',
        'save_audio': True,
        'save_text': True,
        'text_format': 'txt',
    },
    'logging': {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    }
}


class XHSLiveCapturer:
    """
    小红书直播流捕获器
    整合链接转换、流捕获、语音识别功能
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化捕获器
        
        Args:
            config: 配置字典，如果为None则使用默认配置
        """
        self.config = config or DEFAULT_CONFIG
        self._setup_logging()
        
        # 组件
        self._link_converter: Optional[LinkConverter] = None
        self._stream_capturer: Optional[StreamCapturer] = None
        self._speech_manager: Optional[SpeechRecognizerManager] = None
        self._continuous_recognizer = None
        
        # 状态
        self._is_running = False
        self._room_id: Optional[str] = None
        self._stream_info: Optional[Dict] = None
        
        # 输出
        self._output_dir: Optional[Path] = None
        self._text_file: Optional[Path] = None
        self._audio_buffer: list = []
        
        # 回调
        self._on_text_callback = None
        self._on_status_callback = None
        
    def _setup_logging(self):
        """设置日志"""
        log_config = self.config.get('logging', {})
        level = getattr(logging, log_config.get('level', 'INFO'))
        fmt = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        logging.basicConfig(
            level=level,
            format=fmt,
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger('XHSLiveCapturer')
    
    def on_text(self, callback):
        """设置文本输出回调"""
        self._on_text_callback = callback
    
    def on_status(self, callback):
        """设置状态变化回调"""
        self._on_status_callback = callback
    
    def _init_components(self):
        """初始化各组件"""
        self.logger.info("初始化组件...")
        
        # 链接转换器
        self._link_converter = LinkConverter()
        
        # 流捕获器
        stream_config = self.config.get('stream', {})
        self._stream_capturer = StreamCapturer(
            sample_rate=stream_config.get('sample_rate', 16000),
            channels=stream_config.get('channels', 1),
            buffer_size=stream_config.get('buffer_size', 5),
            timeout=stream_config.get('flv_timeout', 30),
            reconnect_interval=stream_config.get('reconnect_interval', 3),
            max_reconnect_attempts=stream_config.get('max_reconnect_attempts', 10),
        )
        
        # 设置流捕获器回调
        self._stream_capturer.on_audio_chunk(self._on_audio_chunk)
        self._stream_capturer.on_status_change(self._on_stream_status)
        self._stream_capturer.on_error(self._on_stream_error)
        
        # 语音识别器
        speech_config = self.config.get('speech_recognition', {})
        self._speech_manager = SpeechRecognizerManager(speech_config)
        
        # 初始化语音识别
        self.logger.info("正在初始化语音识别模型，请稍候...")
        if not self._speech_manager.initialize():
            raise RuntimeError("语音识别模型初始化失败")
        
        # 创建连续识别器
        self._continuous_recognizer = self._speech_manager.create_continuous_recognizer()
        self._continuous_recognizer.on_result(self._on_recognition_result)
        self._continuous_recognizer.on_error(self._on_recognition_error)
        
        self.logger.info("组件初始化完成")
    
    def _setup_output(self, room_id: str):
        """设置输出目录"""
        output_config = self.config.get('output', {})
        save_dir = Path(output_config.get('save_dir', './output'))
        
        # 创建房间专属目录
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._output_dir = save_dir / f"room_{room_id}_{timestamp}"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建文本文件
        text_format = output_config.get('text_format', 'txt')
        self._text_file = self._output_dir / f"transcript.{text_format}"
        
        self.logger.info(f"输出目录: {self._output_dir}")
    
    def convert_url(self, url: str) -> bool:
        """
        转换URL并获取流信息
        
        Args:
            url: 短链接或直播间URL
            
        Returns:
            是否成功
        """
        if not self._link_converter:
            self._init_components()
        
        self.logger.info(f"正在解析链接: {url}")
        
        # 转换短链接并获取房间ID
        long_url, room_id = self._link_converter.convert_short_url(url)
        
        if not room_id:
            self.logger.error("无法从链接中提取房间ID")
            return False
        
        self._room_id = room_id
        self.logger.info(f"链接解析成功!")
        self.logger.info(f"  房间ID: {room_id}")
        self.logger.info(f"  长链接: {long_url[:80]}..." if long_url else "  长链接: N/A")
        
        # 使用CDP获取直播流地址
        self.logger.info("正在获取直播流地址...")
        stream_url = self._link_converter.get_stream_url_via_cdp(room_id, wait_time=15)
        
        if stream_url:
            self._stream_info = {
                'room_id': room_id,
                'flv_url': stream_url,
            }
            self.logger.info(f"  FLV地址: {stream_url[:80]}...")
            
            # 设置输出
            self._setup_output(self._room_id)
            return True
        else:
            self.logger.error("无法获取直播流地址，可能直播已结束")
            return False
    
    def start(self, url: str) -> bool:
        """
        开始捕获和识别
        
        Args:
            url: 短链接或直播间URL
            
        Returns:
            是否成功启动
        """
        # 转换URL
        if not self.convert_url(url):
            return False
        
        # 检查流地址
        stream_url = self._stream_info.get('flv_url') or self._stream_info.get('hls_url')
        if not stream_url:
            self.logger.error("没有找到可用的直播流地址")
            return False
        
        # 启动流捕获
        self.logger.info("正在启动流捕获...")
        if not self._stream_capturer.start(self._stream_info):
            self.logger.error("启动流捕获失败")
            return False
        
        # 启动语音识别
        self.logger.info("正在启动语音识别...")
        self._continuous_recognizer.start()
        
        self._is_running = True
        self.logger.info("=" * 50)
        self.logger.info("捕获已启动，按 Ctrl+C 停止")
        self.logger.info("=" * 50)
        
        if self._on_status_callback:
            self._on_status_callback('started')
        
        return True
    
    def stop(self):
        """停止捕获"""
        self.logger.info("正在停止...")
        self._is_running = False
        
        # 停止流捕获
        if self._stream_capturer:
            self._stream_capturer.stop()
        
        # 停止语音识别
        if self._continuous_recognizer:
            self._continuous_recognizer.stop()
        
        # 保存剩余音频
        self._save_audio_buffer()
        
        if self._on_status_callback:
            self._on_status_callback('stopped')
        
        self.logger.info("已停止")
    
    def _on_audio_chunk(self, chunk: AudioChunk):
        """处理音频数据块"""
        if not self._is_running:
            return
        
        # 保存音频到缓冲区
        output_config = self.config.get('output', {})
        if output_config.get('save_audio', True):
            self._audio_buffer.append(chunk.data)
            
            # 每60秒保存一次
            total_duration = sum(len(d) for d in self._audio_buffer) / (chunk.sample_rate * 2)
            if total_duration >= 60:
                self._save_audio_buffer()
        
        # 发送到语音识别
        if self._continuous_recognizer:
            self._continuous_recognizer.add_audio(
                chunk.data,
                chunk.sample_rate,
                chunk.duration
            )
    
    def _on_stream_status(self, status: StreamStatus):
        """处理流状态变化"""
        self.logger.info(f"流状态: {status.value}")
        
        status_map = {
            StreamStatus.IDLE: 'idle',
            StreamStatus.CONNECTING: 'connecting',
            StreamStatus.CONNECTED: 'connected',
            StreamStatus.STREAMING: 'streaming',
            StreamStatus.RECONNECTING: 'reconnecting',
            StreamStatus.STOPPED: 'stopped',
            StreamStatus.ERROR: 'error',
        }
        
        if self._on_status_callback:
            self._on_status_callback(status_map.get(status, 'unknown'))
    
    def _on_stream_error(self, error: str):
        """处理流错误"""
        self.logger.error(f"流错误: {error}")
    
    def _on_recognition_result(self, result: RecognitionResult):
        """处理识别结果"""
        if not result.text:
            return
        
        # 输出到控制台
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{timestamp}] {result.text}\n")
        
        # 保存到文件
        output_config = self.config.get('output', {})
        if output_config.get('save_text', True) and self._text_file:
            self._save_text(result.text, timestamp)
        
        # 触发回调
        if self._on_text_callback:
            self._on_text_callback(result.text, timestamp)
    
    def _on_recognition_error(self, error: str):
        """处理识别错误"""
        self.logger.error(f"识别错误: {error}")
    
    def _save_text(self, text: str, timestamp: str):
        """保存文本到文件"""
        try:
            with open(self._text_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {text}\n")
        except Exception as e:
            self.logger.error(f"保存文本失败: {e}")
    
    def _save_audio_buffer(self):
        """保存音频缓冲区到文件"""
        if not self._audio_buffer or not self._output_dir:
            return
        
        output_config = self.config.get('output', {})
        if not output_config.get('save_audio', True):
            self._audio_buffer.clear()
            return
        
        try:
            timestamp = datetime.now().strftime('%H%M%S')
            audio_file = self._output_dir / f"audio_{timestamp}.raw"
            
            with open(audio_file, 'wb') as f:
                for chunk in self._audio_buffer:
                    f.write(chunk)
            
            self.logger.debug(f"保存音频: {audio_file}")
            self._audio_buffer.clear()
            
        except Exception as e:
            self.logger.error(f"保存音频失败: {e}")
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def room_id(self) -> Optional[str]:
        return self._room_id
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'room_id': self._room_id,
            'is_running': self._is_running,
        }
        
        if self._stream_capturer:
            stats['stream'] = self._stream_capturer.stats
        
        if self._continuous_recognizer:
            stats['recognition'] = self._continuous_recognizer.stats
        
        return stats


def load_config(config_path: Optional[str] = None) -> Dict:
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()
    
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                # 递归合并配置
                def merge_dict(base, override):
                    for key, value in override.items():
                        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                            merge_dict(base[key], value)
                        else:
                            base[key] = value
                
                merge_dict(config, user_config)
    
    return config


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='小红书直播流捕获器 - 获取直播音频并转换为文字',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
    python main.py http://xhslink.com/m/AZKB2inRqtk
    python main.py https://www.xiaohongshu.com/livestream/570200151527099270
    python main.py -c config.yaml http://xhslink.com/xxx
        '''
    )
    
    parser.add_argument('url', help='小红书直播间短链接或完整URL')
    parser.add_argument('-c', '--config', help='配置文件路径')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细日志')
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 设置详细日志
    if args.verbose:
        config['logging']['level'] = 'DEBUG'
    
    # 创建捕获器
    capturer = XHSLiveCapturer(config)
    
    try:
        # 启动
        if not capturer.start(args.url):
            print("启动失败")
            sys.exit(1)
        
        # 等待用户中断
        while capturer.is_running:
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n用户中断，正在停止...")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        capturer.stop()
        
        # 显示统计
        stats = capturer.get_stats()
        print("\n=== 统计信息 ===")
        if 'stream' in stats:
            print(f"接收时长: {stats['stream'].get('total_duration', 0):.1f} 秒")
            print(f"接收数据: {stats['stream'].get('bytes_received', 0) / 1024:.1f} KB")
        if 'recognition' in stats:
            print(f"识别片段: {stats['recognition'].get('total_chunks', 0)} 个")
            print(f"识别文字: {stats['recognition'].get('total_text_length', 0)} 字符")


if __name__ == "__main__":
    main()