"""
通知模块 - 统一的通知接口
负责：
- 提供统一的 notify() 函数
- 对接 Hermes（待用户确认接口方式）
- 当前使用日志打印作为占位实现
"""

import logging
import os
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


class HermesNotifier:
    """
    Hermes 通知器
    
    注意：目前使用日志打印作为占位实现。
    请用户提供 Hermes 的实际调用方式后，再实现真正的通知逻辑。
    """
    
    def __init__(self):
        """初始化通知器"""
        # 从环境变量读取 Hermes 配置（如果有的话）
        self.hermes_api_url = os.getenv('HERMES_API_URL')
        self.hermes_api_token = os.getenv('HERMES_API_TOKEN')
        self.hermes_cli_path = os.getenv('HERMES_CLI_PATH')
        
        # 标记是否是占位实现
        self.is_placeholder = not (self.hermes_api_url or self.hermes_cli_path)
        
        if self.is_placeholder:
            logger.info("Hermes 未配置，使用占位实现（仅打印日志）")
            logger.info("请提供 Hermes 的调用方式以启用真实通知")
        else:
            logger.info("Hermes 已配置，将使用真实通知")
    
    def notify(self, channel: str, title: str, body: str, url: Optional[str] = None) -> bool:
        """
        发送通知的统一接口
        
        Args:
            channel: 通知渠道 ("email", "discord", "both")
            title: 通知标题
            body: 通知正文
            url: 可选的相关链接
            
        Returns:
            True=成功，False=失败
            
        示例:
            notifier.notify("email", "政策更新", "出入国在留管理庁发布了新规", "https://...")
            notifier.notify("discord", "新职位", "介护职位 - 东京", "https://...")
        """
        if self.is_placeholder:
            return self._placeholder_notify(channel, title, body, url)
        else:
            return self._real_notify(channel, title, body, url)
    
    def _placeholder_notify(self, channel: str, title: str, body: str, 
                            url: Optional[str] = None) -> bool:
        """
        占位实现：打印到日志
        
        当 Hermes 未配置时，将所有通知打印到日志，方便测试流程
        """
        log_msg = f"""
═══════════════════════════════════════════════════════════
【通知占位】渠道：{channel}
标题：{title}
正文：{body}
"""
        if url:
            log_msg += f"链接：{url}\n"
        log_msg += "═══════════════════════════════════════════════════════════"
        
        logger.info(log_msg)
        
        # 模拟成功
        return True
    
    def _real_notify(self, channel: str, title: str, body: str, 
                     url: Optional[str] = None) -> bool:
        """
        真实实现：调用 Hermes
        
        待用户提供 Hermes 接口方式后实现以下两种之一：
        
        方案 A - HTTP API:
            import requests
            response = requests.post(
                self.hermes_api_url,
                json={
                    "channel": channel,
                    "title": title,
                    "body": body,
                    "url": url
                },
                headers={"Authorization": f"Bearer {self.hermes_api_token}"}
            )
            return response.status_code == 200
        
        方案 B - CLI 命令:
            import subprocess
            cmd = [self.hermes_cli_path, "--channel", channel, "--title", title, "--body", body]
            if url:
                cmd.extend(["--url", url])
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        
        请用户提供 Hermes 的具体调用方式后再实现！
        """
        logger.warning("Hermes 已配置但未实现真实通知逻辑")
        logger.warning(f"请检查 HERMES_API_URL 或 HERMES_CLI_PATH 是否正确")
        
        # 暂时降级为占位实现
        return self._placeholder_notify(channel, title, body, url)


# 全局单例
_notifier_instance: Optional[HermesNotifier] = None


def get_notifier() -> HermesNotifier:
    """获取通知器单例"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = HermesNotifier()
    return _notifier_instance


def notify(channel: str, title: str, body: str, url: Optional[str] = None) -> bool:
    """
    便捷函数：发送通知
    
    这是对外暴露的统一接口，其他模块只需调用此函数即可。
    
    Args:
        channel: 通知渠道 ("email", "discord", "both")
        title: 通知标题
        body: 通知正文
        url: 可选的相关链接
        
    Returns:
        True=成功，False=失败
        
    用法:
        from notifier import notify
        notify("email", "政策更新", "出入国在留管理庁发布了新规", "https://...")
    """
    return get_notifier().notify(channel, title, body, url)
