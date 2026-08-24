"""
用户设置管理模块
支持每用户的搜索偏好设置
"""
import json
import os
import tempfile
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from structlog import get_logger

from config import settings as app_settings

logger = get_logger()

# 旧版默认网盘类型，历史用户如果保留这一组值，说明并未主动自定义筛选。
LEGACY_DEFAULT_CLOUD_TYPES = [
    "baidu", "aliyun", "quark", "tianyi", "uc", "mobile",
    "115", "pikpak", "xunlei", "123", "magnet", "ed2k"
]

# 新版默认行为：不传 cloud_types，直接交给上游返回全部类型，避免后续新增网盘类型被 bot 侧白名单挡掉。
DEFAULT_CLOUD_TYPES: list[str] = []
MAX_SETTING_ITEMS = 32
MAX_SETTING_ITEM_LENGTH = 128

# 网盘类型中文名
CLOUD_TYPE_NAMES = {
    "baidu": "百度网盘",
    "aliyun": "阿里云盘",
    "quark": "夸克网盘",
    "guangya": "光鸭云盘",
    "tianyi": "天翼云盘",
    "uc": "UC网盘",
    "mobile": "移动云盘",
    "115": "115网盘",
    "pikpak": "PikPak",
    "xunlei": "迅雷网盘",
    "123": "123网盘",
    "weiyun": "腾讯微云",
    "lanzou": "蓝奏云",
    "jianguoyun": "坚果云",
    "magnet": "磁力链接",
    "ed2k": "电驴链接",
    "others": "其他"
}


@dataclass
class FilterSettings:
    """过滤设置"""
    include: List[str] = None  # 必须包含的关键词
    exclude: List[str] = None  # 排除的关键词
    
    def __post_init__(self):
        if self.include is None:
            self.include = []
        if self.exclude is None:
            self.exclude = []


@dataclass
class UserSettings:
    """用户设置"""
    user_id: int
    # 网盘类型筛选
    cloud_types: List[str] = None
    # 过滤设置
    filter_include: List[str] = None
    filter_exclude: List[str] = None
    # 默认结果限制
    result_limit: int = 10
    # 默认搜索来源
    source_type: str = "all"  # all, tg, plugin
    # 默认频道
    channels: List[str] = None
    # 默认插件
    plugins: List[str] = None
    
    def __post_init__(self):
        if self.cloud_types is None:
            self.cloud_types = DEFAULT_CLOUD_TYPES.copy()
        if self.filter_include is None:
            self.filter_include = []
        if self.filter_exclude is None:
            self.filter_exclude = []
        if self.channels is None:
            self.channels = []
        if self.plugins is None:
            self.plugins = []
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        if not isinstance(data, dict):
            raise ValueError("settings payload must be an object")

        allowed = {
            "user_id", "cloud_types", "filter_include", "filter_exclude",
            "result_limit", "source_type", "channels", "plugins",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError("settings payload contains unknown fields")

        user_id = data.get("user_id")
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        for key in ("cloud_types", "filter_include", "filter_exclude", "channels", "plugins"):
            value = data.get(key)
            if value is not None and (
                not isinstance(value, list)
                or any(not isinstance(item, str) for item in value)
            ):
                raise ValueError(f"{key} must be a list of strings")
            if value is not None and len(value) > MAX_SETTING_ITEMS:
                raise ValueError(f"{key} contains too many items")
            if value is not None and any(len(item) > MAX_SETTING_ITEM_LENGTH for item in value):
                raise ValueError(f"{key} contains an oversized item")

        result_limit = data.get("result_limit", app_settings.default_result_limit)
        if (
            isinstance(result_limit, bool)
            or not isinstance(result_limit, int)
            or not 1 <= result_limit <= app_settings.max_result_limit
        ):
            raise ValueError("result_limit is out of range")

        source_type = data.get("source_type", "all")
        if source_type not in {"all", "tg", "plugin"}:
            raise ValueError("source_type is invalid")

        return cls(**data)
    
    def get_filter_config(self) -> Optional[dict]:
        """获取过滤配置用于 API 调用"""
        filter_config = {}
        if self.filter_include:
            filter_config["include"] = self.filter_include
        if self.filter_exclude:
            filter_config["exclude"] = self.filter_exclude
        return filter_config if filter_config else None
    
    def format_display(self) -> str:
        """格式化显示设置"""
        lines = [
            "⚙️ *当前设置*\n",
            f"📊 结果数量: `{self.result_limit}`",
            f"🔍 搜索来源: `{self.source_type}`",
        ]
        
        # 网盘类型
        if self.cloud_types:
            type_names = [CLOUD_TYPE_NAMES.get(t, t) for t in self.cloud_types[:5]]
            if len(self.cloud_types) > 5:
                type_names.append(f"等{len(self.cloud_types)}个")
            lines.append(f"📁 网盘类型: {', '.join(type_names)}")
        else:
            lines.append("📁 网盘类型: 全部")
        
        # 过滤设置
        if self.filter_include:
            lines.append(f"✅ 包含过滤: {', '.join(self.filter_include)}")
        if self.filter_exclude:
            lines.append(f"❌ 排除过滤: {', '.join(self.filter_exclude)}")
        
        if self.channels:
            lines.append(f"📡 指定频道: {len(self.channels)}个")
        else:
            lines.append("📡 指定频道: 全部")
        if self.plugins:
            lines.append(f"🔌 指定插件: {len(self.plugins)}个")
        else:
            lines.append("🔌 指定插件: 全部")
        
        return "\n".join(lines)


class SettingsManager:
    """设置管理器"""
    
    def __init__(self, data_dir: str | Path | None = None, max_cache_size: int = 2048):
        self.data_dir = Path(data_dir or app_settings.data_dir)
        self.max_cache_size = max_cache_size
        self.settings_cache: OrderedDict[int, UserSettings] = OrderedDict()
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)
    
    def _get_settings_file(self, user_id: int) -> Path:
        """获取用户设置文件路径"""
        return self.data_dir / f"user_{user_id}.json"

    def _cache_settings(self, settings: UserSettings) -> None:
        self.settings_cache[settings.user_id] = settings
        self.settings_cache.move_to_end(settings.user_id)
        while len(self.settings_cache) > self.max_cache_size:
            self.settings_cache.popitem(last=False)

    @staticmethod
    def _quarantine_invalid_file(path: Path) -> Path:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        target = path.with_name(f"{path.name}.invalid-{stamp}-{time.time_ns()}")
        os.replace(path, target)
        os.chmod(target, 0o600)
        return target
    
    def get_settings(self, user_id: int) -> UserSettings:
        """获取用户设置（优先从缓存）"""
        if user_id in self.settings_cache:
            self.settings_cache.move_to_end(user_id)
            return self.settings_cache[user_id]
        
        # 尝试从文件加载
        settings_file = self._get_settings_file(user_id)
        if settings_file.exists():
            try:
                with settings_file.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    settings = UserSettings.from_dict(data)
                    if settings.user_id != user_id:
                        raise ValueError("settings file user_id mismatch")
                    if settings.cloud_types == LEGACY_DEFAULT_CLOUD_TYPES:
                        settings.cloud_types = DEFAULT_CLOUD_TYPES.copy()
                        self.save_settings(settings)
                    else:
                        os.chmod(settings_file, 0o600)
                    self._cache_settings(settings)
                    return settings
            except Exception as e:
                self._quarantine_invalid_file(settings_file)
                logger.error("load_settings_failed", error_type=type(e).__name__, quarantined=True)
        
        # 创建默认设置
        settings = UserSettings(user_id=user_id)
        self.save_settings(settings)
        return settings
    
    def save_settings(self, settings: UserSettings):
        """保存用户设置"""
        settings = UserSettings.from_dict(settings.to_dict())
        settings_file = self._get_settings_file(settings.user_id)
        temp_path: Optional[Path] = None
        try:
            fd, raw_temp_path = tempfile.mkstemp(
                prefix=".settings-",
                suffix=".tmp",
                dir=self.data_dir,
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, settings_file)
            temp_path = None
            directory_fd = os.open(self.data_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self._cache_settings(settings)
        except Exception as e:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            logger.error("save_settings_failed", error_type=type(e).__name__)
            raise
    
    def update_settings(self, user_id: int, **kwargs) -> UserSettings:
        """更新用户设置"""
        settings = self.get_settings(user_id)
        updated = settings.to_dict()
        for key, value in kwargs.items():
            if key not in updated:
                raise ValueError(f"unknown settings field: {key}")
            updated[key] = value

        settings = UserSettings.from_dict(updated)
        self.save_settings(settings)
        return settings
    
    def reset_settings(self, user_id: int) -> UserSettings:
        """重置用户设置为默认"""
        settings = UserSettings(user_id=user_id)
        self.save_settings(settings)
        self._cache_settings(settings)
        return settings

    def clear_cache(self) -> int:
        """清理内存中的设置缓存。"""
        count = len(self.settings_cache)
        self.settings_cache.clear()
        return count


# 全局设置管理器实例
settings_manager = SettingsManager()
