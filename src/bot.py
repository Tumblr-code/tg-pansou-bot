#!/usr/bin/env python3
"""
Telegram Bot 主模块 - 支持分类按钮
"""
import asyncio
import html
import sys

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from structlog import get_logger

from application_factory import BotHandlerSet
from application_factory import create_application as build_application
from config import settings
from pansou_client import pansou_client, CLOUD_TYPE_NAMES, CLOUD_TYPE_ICONS
from user_settings import settings_manager, CLOUD_TYPE_NAMES as SETTINGS_CLOUD_NAMES
from keyboards import (
    create_all_results_keyboard,
    create_pagination_keyboard,
    create_type_keyboard,
    is_cache_owner as _is_cache_owner,
    parse_cache_key_from_action as _parse_cache_key_from_action,
    parse_type_callback as _parse_type_callback,
)
from maintenance import (
    PIP_INSTALL_TIMEOUT,
    REPO_ROOT,
    restart_process as _restart_process,
    run_command as _run_command,
    run_git_command as _run_git_command,
    truncate_output as _truncate_output,
)
from message_utils import (
    add_auto_delete_notice,
    ensure_telegram_text,
    reply_with_auto_delete,
    safe_edit_message as _safe_edit_message,
)
from runtime_state import (
    auto_delete_message,
    check_search_rate_limit,
    schedule_message_deletion,
    search_cache,
    search_rate_limiter,
    set_bot_application,
)
from search_options import (
    format_compact_list as _format_compact_list,
    get_list_arg as _get_list_arg,
    get_pansou_lists as _get_pansou_lists,
    parse_csv_values as _parse_csv_values,
    parse_search_options as _parse_search_options,
    validate_values as _validate_values,
)
from search_flow import perform_search, perform_search_from_callback

logger = get_logger()

BOT_COMMANDS = [
    BotCommand("search", "搜索资源"),
    BotCommand("s", "群组内搜索资源"),
    BotCommand("help", "查看帮助"),
    BotCommand("settings", "查看或修改搜索设置"),
    BotCommand("types", "查看支持网盘类型"),
    BotCommand("sources", "查看来源概况"),
    BotCommand("plugins", "查看启用插件"),
    BotCommand("channels", "查看启用频道"),
    BotCommand("filter", "管理关键词过滤"),
    BotCommand("reset", "重置搜索设置"),
    BotCommand("status", "检查服务状态"),
    BotCommand("refresh", "刷新运行时缓存"),
]

# ============ 权限检查 ============

def is_admin(user_id: int) -> bool:
    """检查用户是否为管理员"""
    return settings.is_admin(user_id)


def check_admin_permission(update: Update) -> bool:
    """检查用户是否有管理员权限，无权限时发送提示"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return False
    return True


# ============ 命令处理函数 ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令"""
    user = update.effective_user
    is_user_admin = is_admin(user.id)
    safe_first_name = html.escape(user.first_name or "朋友")
    
    if is_user_admin:
        # 管理员看到完整功能
        welcome_text = f"""👋 你好，{safe_first_name}！

我是 <b>网盘搜索机器人</b>，可以帮你搜索各种网盘资源。

<b>🎯 使用方式：</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令： <code>/search 钢铁侠</code>
• 群里使用：<code>/s 钢铁侠</code>

<b>✨ 特色功能：</b>
• 📂 搜索结果分类显示，按需查看
• 🔍 支持多种网盘类型筛选
• ⚙️ 个人设置持久化
• 🔗 一键复制链接和密码

<b>🔧 管理员命令：</b>
/settings - 查看/修改个人设置
/types - 查看支持的网盘类型
/sources - 查看来源概况
/plugins - 查看/设置插件来源
/channels - 查看/设置频道来源
/filter - 设置搜索过滤器
/reset - 重置搜索设置
/status - 检查服务状态
/refresh - 刷新运行时状态
/update - 拉取最新代码并重启
/help - 查看详细帮助

👑 <b>你是管理员，拥有所有权限</b>"""
    else:
        # 普通用户只看到简单搜索功能
        welcome_text = f"""👋 你好，{safe_first_name}！

我是 <b>网盘搜索机器人</b>，可以帮你搜索各种网盘资源。

<b>🎯 使用方式：</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令： <code>/search 钢铁侠</code>
• 群里使用：<code>/s 钢铁侠</code>

<b>📁 支持的网盘：</b>
百度、阿里、夸克、光鸭、天翼、UC、115、PikPak、迅雷、123、微云、蓝奏、坚果云、磁力、电驴

💡 <b>提示：</b>搜索后会显示网盘类型按钮，点击即可查看结果

/help - 查看帮助"""
    
    await reply_with_auto_delete(update, welcome_text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /help 命令"""
    user_id = update.effective_user.id
    is_user_admin = is_admin(user_id)
    
    if is_user_admin:
        # 管理员看到完整帮助
        help_text = """<b>📖 管理员使用帮助</b>

<b>🔍 基础搜索</b>
• 直接发送： <code>复仇者联盟</code>
• 命令搜索： <code>/search 钢铁侠</code>
• 群聊搜索： <code>/s 钢铁侠</code>
• 指定来源： <code>/search 钢铁侠 --src plugin --plugins panta,wanou --types quark,aliyun --limit 10 --refresh</code>

<b>📂 分类查看</b>
搜索后会显示网盘类型按钮，点击即可查看该类型的资源：
🔴 百度网盘 (12)  🟠 夸克网盘 (8)
🔵 阿里云盘 (5)   🧲 磁力链接 (3)

<b>⚙️ 设置管理</b>
• <code>/settings</code> - 查看设置
• <code>/settings types baidu,quark</code> - 设置默认网盘
• <code>/settings plugins panta,wanou</code> - 设置默认插件
• <code>/settings channels tgsearchers4</code> - 设置默认频道
• <code>/settings limit 15</code> - 设置结果数量
• <code>/settings reset</code> - 重置设置

<b>🔍 过滤器</b>
• <code>/filter add 包含 1080P</code>
• <code>/filter add 排除 预告</code>
• <code>/filter clear</code> - 清除过滤

<b>♻️ 运行维护</b>
• <code>/status</code> - 查看服务状态
• <code>/sources</code> - 查看来源概况
• <code>/plugins</code> - 查看启用插件
• <code>/channels</code> - 查看启用频道
• <code>/reset</code> - 重置搜索设置
• <code>/refresh</code> - 刷新缓存和连接状态
• <code>/update</code> - 拉取最新代码并重启

<b>📁 支持的网盘</b>
百度、阿里、夸克、光鸭、天翼、UC、115、PikPak、迅雷、123、微云、蓝奏、坚果云、磁力、电驴"""
    else:
        # 普通用户只看到简单帮助
        help_text = """<b>📖 使用帮助</b>

<b>🔍 基础搜索</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令：<code>/search 钢铁侠</code>
• 群里使用：<code>/s 钢铁侠</code>

<b>📂 分类查看</b>
搜索后会显示网盘类型按钮，点击即可查看该类型的资源：
🔴 百度网盘 (12)  🟠 夸克网盘 (8)
🔵 阿里云盘 (5)   🧲 磁力链接 (3)

<b>📁 支持的网盘</b>
百度、阿里、夸克、光鸭、天翼、UC、115、PikPak、迅雷、123、微云、蓝奏、坚果云、磁力、电驴

💡 发送关键词即可开始搜索！"""
    
    await reply_with_auto_delete(update, help_text, parse_mode=ParseMode.HTML)


async def types_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /types 命令 - 显示支持的网盘类型（仅管理员）"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return
    
    lines = ["📁 <b>支持的网盘类型</b>\n"]
    
    for code, name in CLOUD_TYPE_NAMES.items():
        icon = CLOUD_TYPE_ICONS.get(code, "📁")
        lines.append(f"{icon} <b>{name}</b> - <code>{code}</code>")
    
    lines.append("\n<b>使用示例：</b>")
    lines.append("<code>/settings types baidu,quark</code>")
    
    await reply_with_auto_delete(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def plugins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /plugins 命令 - 显示当前 Pansou API 启用插件。"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    plugins, _ = await _get_pansou_lists(force_refresh=True)
    text = (
        f"🔌 <b>当前启用插件</b>\n\n"
        f"数量: <code>{len(plugins)}</code>\n\n"
        f"{_format_compact_list(plugins)}\n\n"
        "<b>设置示例：</b>\n"
        "<code>/settings plugins panta,wanou,quark4k</code>\n"
        "<code>/settings plugins all</code>"
    )
    await reply_with_auto_delete(update, text, parse_mode=ParseMode.HTML)


async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /channels 命令 - 显示当前 Pansou API 启用频道。"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    _, channels = await _get_pansou_lists(force_refresh=True)
    text = (
        f"📡 <b>当前启用频道</b>\n\n"
        f"数量: <code>{len(channels)}</code>\n\n"
        f"{_format_compact_list(channels)}\n\n"
        "<b>设置示例：</b>\n"
        "<code>/settings channels tgsearchers4,Aliyun_4K_Movies</code>\n"
        "<code>/settings channels all</code>"
    )
    await reply_with_auto_delete(update, text, parse_mode=ParseMode.HTML)


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /sources 命令 - 汇总当前 Pansou API 来源配置。"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    plugins, channels = await _get_pansou_lists(force_refresh=True)
    text = (
        "🧭 <b>来源概况</b>\n\n"
        f"🔌 插件: <code>{len(plugins)}</code> 个\n"
        f"📡 频道: <code>{len(channels)}</code> 个\n\n"
        "<b>常用命令：</b>\n"
        "<code>/plugins</code> 查看插件列表\n"
        "<code>/channels</code> 查看频道列表\n"
        "<code>/settings source all</code> 搜索全部来源\n"
        "<code>/settings source plugin</code> 只搜插件\n"
        "<code>/settings source tg</code> 只搜频道"
    )
    await reply_with_auto_delete(update, text, parse_mode=ParseMode.HTML)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /reset 命令 - 快速重置当前用户搜索设置。"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    settings_manager.reset_settings(update.effective_user.id)
    await reply_with_auto_delete(update, "✅ 搜索设置已恢复默认：全部来源、全部网盘、全部插件和频道")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /settings 命令 - 管理用户设置（仅管理员）"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return
    
    user_id = update.effective_user.id
    args = context.args
    
    if not args or args[0] == "show":
        user_settings = settings_manager.get_settings(user_id)
        await reply_with_auto_delete(update, user_settings.format_display(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0] == "reset":
        settings_manager.reset_settings(user_id)
        await reply_with_auto_delete(update, "✅ 设置已重置为默认值")
        return
    
    if args[0] == "types" and len(args) > 1:
        types_str = _get_list_arg(args)
        if types_str.lower() in ("all", "clear", "全部"):
            settings_manager.update_settings(user_id, cloud_types=[])
            await reply_with_auto_delete(update, "✅ 网盘类型已设置为：全部")
            return

        cloud_types = _parse_csv_values(types_str)
        
        valid_types = []
        invalid_types = []
        for t in cloud_types:
            if t in SETTINGS_CLOUD_NAMES:
                valid_types.append(t)
            else:
                invalid_types.append(t)
        
        if valid_types:
            settings_manager.update_settings(user_id, cloud_types=valid_types)
            type_names = [SETTINGS_CLOUD_NAMES[t] for t in valid_types]
            msg = f"✅ 已设置搜索网盘类型：{', '.join(type_names)}"
            if invalid_types:
                msg += f"\n⚠️ 无效类型：{', '.join(invalid_types)}"
            await reply_with_auto_delete(update, msg)
        else:
            await reply_with_auto_delete(
                update,
                f"❌ 无效的类型：{', '.join(invalid_types)}\n"
                f"使用 /types 查看支持的类型"
            )
        return

    if args[0] == "plugins" and len(args) > 1:
        plugins_str = _get_list_arg(args)
        if plugins_str.lower() in ("all", "clear", "全部"):
            settings_manager.update_settings(user_id, plugins=[])
            await reply_with_auto_delete(update, "✅ 插件来源已设置为：全部启用插件")
            return

        requested_plugins = _parse_csv_values(plugins_str)
        available_plugins, _ = await _get_pansou_lists()
        valid_plugins, invalid_plugins = _validate_values(requested_plugins, available_plugins)
        if valid_plugins:
            settings_manager.update_settings(user_id, plugins=valid_plugins)
            msg = f"✅ 已设置插件来源：{', '.join(valid_plugins)}"
            if invalid_plugins:
                msg += f"\n⚠️ 无效插件：{', '.join(invalid_plugins)}"
            await reply_with_auto_delete(update, msg)
        else:
            await reply_with_auto_delete(
                update,
                f"❌ 无效插件：{', '.join(invalid_plugins or requested_plugins)}\n"
                f"使用 /plugins 查看当前启用插件"
            )
        return

    if args[0] == "channels" and len(args) > 1:
        channels_str = _get_list_arg(args)
        if channels_str.lower() in ("all", "clear", "全部"):
            settings_manager.update_settings(user_id, channels=[])
            await reply_with_auto_delete(update, "✅ 频道来源已设置为：全部默认频道")
            return

        requested_channels = _parse_csv_values(channels_str)
        _, available_channels = await _get_pansou_lists()
        valid_channels, invalid_channels = _validate_values(requested_channels, available_channels)
        if valid_channels:
            settings_manager.update_settings(user_id, channels=valid_channels)
            msg = f"✅ 已设置频道来源：{', '.join(valid_channels)}"
            if invalid_channels:
                msg += f"\n⚠️ 无效频道：{', '.join(invalid_channels)}"
            await reply_with_auto_delete(update, msg)
        else:
            await reply_with_auto_delete(
                update,
                f"❌ 无效频道：{', '.join(invalid_channels or requested_channels)}\n"
                f"使用 /channels 查看当前启用频道"
            )
        return
    
    if args[0] == "limit" and len(args) > 1:
        try:
            limit = int(args[1])
            if 1 <= limit <= settings.max_result_limit:
                settings_manager.update_settings(user_id, result_limit=limit)
                await reply_with_auto_delete(update, f"✅ 结果数量限制已设置为 {limit}")
            else:
                await reply_with_auto_delete(update, f"❌ 限制范围：1-{settings.max_result_limit}")
        except ValueError:
            await reply_with_auto_delete(update, "❌ 请输入数字")
        return
    
    if args[0] == "source" and len(args) > 1:
        source = args[1].lower()
        if source in ["all", "tg", "plugin"]:
            settings_manager.update_settings(user_id, source_type=source)
            source_names = {"all": "全部", "tg": "Telegram", "plugin": "插件"}
            await reply_with_auto_delete(update, f"✅ 搜索来源已设置为：{source_names[source]}")
        else:
            await reply_with_auto_delete(update, "❌ 无效来源，可选：all, tg, plugin")
        return
    
    help_text = """<b>⚙️ 设置命令</b>

<code>/settings</code> - 查看当前设置
<code>/settings reset</code> - 重置为默认
<code>/settings types baidu,quark</code> - 设置网盘类型
<code>/settings types all</code> - 恢复全部网盘
<code>/settings plugins panta,wanou</code> - 指定插件
<code>/settings plugins all</code> - 恢复全部插件
<code>/settings channels tgsearchers4</code> - 指定频道
<code>/settings channels all</code> - 恢复全部频道
<code>/settings limit 15</code> - 设置结果数量
<code>/settings source all</code> - 设置搜索来源"""
    await reply_with_auto_delete(update, help_text, parse_mode=ParseMode.HTML)


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /filter 命令 - 管理搜索过滤器（仅管理员）"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return
    
    user_id = update.effective_user.id
    args = context.args
    
    user_settings = settings_manager.get_settings(user_id)
    
    if not args:
        lines = ["🔍 <b>当前过滤器设置</b>\n"]
        
        if user_settings.filter_include:
            lines.append(f"<b>✅ 包含关键词：</b>")
            for word in user_settings.filter_include:
                lines.append(f"  • {word}")
        else:
            lines.append("<b>✅ 包含关键词：</b> 无")
        
        lines.append("")
        
        if user_settings.filter_exclude:
            lines.append(f"<b>❌ 排除关键词：</b>")
            for word in user_settings.filter_exclude:
                lines.append(f"  • {word}")
        else:
            lines.append("<b>❌ 排除关键词：</b> 无")
        
        lines.append("\n<b>操作命令：</b>")
        lines.append("<code>/filter add 包含 1080P</code>")
        lines.append("<code>/filter add 排除 预告</code>")
        lines.append("<code>/filter clear</code>")
        
        await reply_with_auto_delete(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return
    
    action = args[0].lower()
    
    if action == "clear":
        user_settings.filter_include = []
        user_settings.filter_exclude = []
        settings_manager.save_settings(user_settings)
        await reply_with_auto_delete(update, "✅ 过滤器已清除")
        return
    
    if action in ["add", "remove"] and len(args) >= 3:
        filter_type = args[1].lower()
        keyword = " ".join(args[2:])
        
        if filter_type not in ["包含", "include", "exclude", "排除"]:
            await reply_with_auto_delete(update, "❌ 类型必须是：包含/include 或 排除/exclude")
            return
        
        is_include = filter_type in ["包含", "include"]
        target_list = user_settings.filter_include if is_include else user_settings.filter_exclude
        
        if action == "add":
            if keyword not in target_list:
                target_list.append(keyword)
                settings_manager.save_settings(user_settings)
            type_name = "包含" if is_include else "排除"
            await reply_with_auto_delete(update, f"✅ 已添加{type_name}关键词：{keyword}")
        else:
            if keyword in target_list:
                target_list.remove(keyword)
                settings_manager.save_settings(user_settings)
                type_name = "包含" if is_include else "排除"
                await reply_with_auto_delete(update, f"✅ 已移除{type_name}关键词：{keyword}")
            else:
                await reply_with_auto_delete(update, f"⚠️ 关键词不存在：{keyword}")
        return
    
    await reply_with_auto_delete(
        update,
        "<b>🔍 过滤器命令</b>\n\n"
        "<code>/filter</code> - 查看过滤器\n"
        "<code>/filter add 包含 1080P</code>\n"
        "<code>/filter add 排除 预告</code>\n"
        "<code>/filter clear</code>",
        parse_mode=ParseMode.HTML
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /status 命令"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    user_id = update.effective_user.id
    message = await update.message.reply_text("🔄 正在检查服务状态...")
    auto_delete_message(message)
    
    service_info = await pansou_client.get_service_info(force_refresh=True)
    is_healthy = bool(service_info.get("healthy"))
    
    if is_healthy:
        user_settings = settings_manager.get_settings(user_id)
        plugin_count = service_info.get("plugin_count", len(service_info.get("plugins", [])))
        channels_count = service_info.get("channels_count", len(service_info.get("channels", [])))
        status_text = f"""✅ <b>服务状态正常</b>

🤖 Bot: 运行中
🔍 Pansou API: 正常
🔌 启用插件: {plugin_count}
📡 默认频道: {channels_count}

<b>您的设置：</b>
📊 结果限制: {user_settings.result_limit}
🔍 搜索来源: {user_settings.source_type}
📁 网盘类型: {"全部" if not user_settings.cloud_types else str(len(user_settings.cloud_types)) + "个"}
🔌 插件筛选: {"全部" if not user_settings.plugins else str(len(user_settings.plugins)) + "个"}
📡 频道筛选: {"全部" if not user_settings.channels else str(len(user_settings.channels)) + "个"}
✅ 包含过滤: {len(user_settings.filter_include)}个
❌ 排除过滤: {len(user_settings.filter_exclude)}个

👑 你是管理员"""
    else:
        status_text = """⚠️ <b>服务异常</b>

🤖 Bot: 运行中
🔍 Pansou API: 无法连接

请稍后重试..."""
    
    # 添加自动删除提示
    status_text = add_auto_delete_notice(status_text, ParseMode.HTML)
    await _safe_edit_message(message.edit_text, status_text, parse_mode=ParseMode.HTML)


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /refresh 命令 - 刷新运行时缓存与连接状态"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    message = await update.message.reply_text("🔄 正在刷新运行时状态...")
    auto_delete_message(message)

    cleared_search_cache = search_cache.clear()
    cleared_rate_limiters = search_rate_limiter.clear()
    cleared_settings_cache = settings_manager.clear_cache()
    pansou_client.clear_runtime_cache()
    is_healthy = await pansou_client.health_check(force_refresh=True)

    status_icon = "✅" if is_healthy else "⚠️"
    status_text = f"""{status_icon} <b>运行时状态已更新</b>

🧹 搜索缓存已清理: {cleared_search_cache} 条
🚦 限流记录已清理: {cleared_rate_limiters} 个用户
⚙️ 设置缓存已清理: {cleared_settings_cache} 个用户
🔍 Pansou API: {"正常" if is_healthy else "无法连接"}"""

    status_text = add_auto_delete_notice(status_text, ParseMode.HTML)
    await _safe_edit_message(message.edit_text, status_text, parse_mode=ParseMode.HTML)

    logger.info(
        "runtime_state_updated",
        cleared_search_cache=cleared_search_cache,
        cleared_rate_limiters=cleared_rate_limiters,
        cleared_settings_cache=cleared_settings_cache,
        pansou_healthy=is_healthy,
        user_id=update.effective_user.id,
    )


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /update 命令 - 拉取最新代码并重启"""
    if not check_admin_permission(update):
        await reply_with_auto_delete(update, "⛔️ 该命令仅限管理员使用")
        return

    message = await update.message.reply_text("🔄 正在检查 GitHub 更新...")
    auto_delete_message(message)

    if not (REPO_ROOT / ".git").exists():
        text = add_auto_delete_notice("❌ 当前运行目录不是 Git 仓库，无法自动更新", ParseMode.HTML)
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, branch, error = await _run_command("git", "branch", "--show-current")
    if code != 0 or not branch:
        detail = html.escape(_truncate_output(error or "无法识别当前分支"))
        text = add_auto_delete_notice(
            f"❌ 无法识别当前分支\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, status_output, error = await _run_command("git", "status", "--porcelain")
    if code != 0:
        detail = html.escape(_truncate_output(error or status_output or "无法检查仓库状态"))
        text = add_auto_delete_notice(
            f"❌ 无法检查仓库状态\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    if status_output:
        detail = html.escape(_truncate_output(status_output, limit=600))
        text = add_auto_delete_notice(
            "⚠️ 检测到本地有未提交修改，已取消自动更新\n\n"
            "请先提交或清理本地改动后再执行 /update\n\n"
            f"<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, current_head, error = await _run_command("git", "rev-parse", "HEAD")
    if code != 0 or not current_head:
        detail = html.escape(_truncate_output(error or "无法读取当前版本"))
        text = add_auto_delete_notice(
            f"❌ 无法读取当前版本\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    await _safe_edit_message(
        message.edit_text,
        f"🔄 正在从 GitHub 拉取更新...\n\n分支: <code>{html.escape(branch)}</code>",
        parse_mode=ParseMode.HTML,
    )

    code, fetch_output, fetch_error = await _run_git_command("fetch", "origin", branch)
    if code != 0:
        detail = html.escape(_truncate_output(fetch_error or fetch_output or "git fetch 失败"))
        text = add_auto_delete_notice(
            f"❌ 拉取远端信息失败\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, remote_head, error = await _run_command("git", "rev-parse", f"origin/{branch}")
    if code != 0 or not remote_head:
        detail = html.escape(_truncate_output(error or "无法读取远端版本"))
        text = add_auto_delete_notice(
            f"❌ 无法读取远端版本\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    current_short = html.escape(current_head[:7])
    remote_short = html.escape(remote_head[:7])
    safe_branch = html.escape(branch)

    if current_head == remote_head:
        text = add_auto_delete_notice(
            "✅ 当前已经是最新版本\n\n"
            f"分支: <code>{safe_branch}</code>\n"
            f"版本: <code>{current_short}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    await _safe_edit_message(
        message.edit_text,
        "⬇️ 发现新版本，正在更新代码...\n\n"
        f"分支: <code>{safe_branch}</code>\n"
        f"当前: <code>{current_short}</code>\n"
        f"远端: <code>{remote_short}</code>",
        parse_mode=ParseMode.HTML,
    )

    code, pull_output, pull_error = await _run_command("git", "merge", "--ff-only", f"origin/{branch}")
    if code != 0:
        detail = html.escape(_truncate_output(pull_error or pull_output or "git merge 失败"))
        text = add_auto_delete_notice(
            f"❌ 更新代码失败\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, new_head, error = await _run_command("git", "rev-parse", "HEAD")
    if code != 0 or not new_head:
        detail = html.escape(_truncate_output(error or "更新后无法读取版本"))
        text = add_auto_delete_notice(
            f"⚠️ 代码已拉取，但无法读取更新后的版本\n\n<code>{detail}</code>",
            ParseMode.HTML,
        )
        await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
        return

    code, changed_files_output, changed_files_error = await _run_command(
        "git", "diff", "--name-only", current_head, new_head
    )
    changed_files = set(changed_files_output.splitlines()) if code == 0 else set()

    if "requirements.txt" in changed_files:
        await _safe_edit_message(
            message.edit_text,
            "📦 代码更新完成，正在安装依赖...\n\n"
            f"新版本: <code>{html.escape(new_head[:7])}</code>",
            parse_mode=ParseMode.HTML,
        )
        code, pip_output, pip_error = await _run_command(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            "requirements.txt",
            timeout=PIP_INSTALL_TIMEOUT,
        )
        if code != 0:
            detail = html.escape(_truncate_output(pip_error or pip_output or "依赖安装失败"))
            text = add_auto_delete_notice(
                "⚠️ 代码已更新，但依赖安装失败，已取消自动重启\n\n"
                f"当前版本: <code>{html.escape(new_head[:7])}</code>\n\n"
                f"<code>{detail}</code>",
                ParseMode.HTML,
            )
            await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
            return

    logger.info(
        "bot_update_applied",
        branch=branch,
        old_head=current_head[:7],
        new_head=new_head[:7],
        user_id=update.effective_user.id,
    )

    text = add_auto_delete_notice(
        "✅ 更新成功，正在重启机器人...\n\n"
        f"分支: <code>{safe_branch}</code>\n"
        f"旧版本: <code>{current_short}</code>\n"
        f"新版本: <code>{html.escape(new_head[:7])}</code>",
        ParseMode.HTML,
    )
    await _safe_edit_message(message.edit_text, text, parse_mode=ParseMode.HTML)
    asyncio.create_task(_restart_process())


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /search 命令"""
    args = context.args
    if not args:
        await reply_with_auto_delete(
            update,
            "❌ 请输入搜索关键词\n\n"
            "示例：\n"
            "<code>/search 复仇者联盟</code>\n"
            "<code>/search 钢铁侠</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    keyword, options, error = _parse_search_options(" ".join(args))
    if error:
        await reply_with_auto_delete(update, f"❌ {html.escape(error)}", parse_mode=ParseMode.HTML)
        return
    if not keyword:
        await reply_with_auto_delete(update, "❌ 请输入搜索关键词", parse_mode=ParseMode.HTML)
        return

    if options.get("cloud_types"):
        valid_types, invalid_types = _validate_values(options["cloud_types"], list(SETTINGS_CLOUD_NAMES.keys()))
        if invalid_types:
            await reply_with_auto_delete(
                update,
                f"❌ 无效网盘类型：{html.escape(', '.join(invalid_types))}\n使用 /types 查看支持的类型",
                parse_mode=ParseMode.HTML,
            )
            return
        options["cloud_types"] = valid_types

    if options.get("plugins") or options.get("channels"):
        available_plugins, available_channels = await _get_pansou_lists()
        if options.get("plugins"):
            valid_plugins, invalid_plugins = _validate_values(options["plugins"], available_plugins)
            if invalid_plugins:
                await reply_with_auto_delete(
                    update,
                    f"❌ 无效插件：{html.escape(', '.join(invalid_plugins))}\n使用 /plugins 查看当前启用插件",
                    parse_mode=ParseMode.HTML,
                )
                return
            options["plugins"] = valid_plugins
        if options.get("channels"):
            valid_channels, invalid_channels = _validate_values(options["channels"], available_channels)
            if invalid_channels:
                await reply_with_auto_delete(
                    update,
                    f"❌ 无效频道：{html.escape(', '.join(invalid_channels))}\n使用 /channels 查看当前启用频道",
                    parse_mode=ParseMode.HTML,
                )
                return
            options["channels"] = valid_channels

    await perform_search(update, context, keyword, **options)


async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理私聊消息（直接作为搜索关键词）"""
    if not update.message or not update.message.text:
        return
    
    if update.message.text.startswith('/'):
        return
    
    keyword = update.message.text.strip()
    if len(keyword) < 2:
        await reply_with_auto_delete(update, "⚠️ 搜索关键词至少需要2个字符")
        return
    
    await perform_search(update, context, keyword)

# ============ 回调处理 ============

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    query = update.callback_query
    data = query.data
    if not data:
        return

    if data == "noop":
        await query.answer("正在重新搜索...")
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = query.message.message_id if query.message else None
    if message_id is None:
        await query.answer("❌ 搜索消息不可用", show_alert=True)
        return
    
    # 处理刷新
    if data.startswith("refresh:"):
        cache_key = _parse_cache_key_from_action(data, "refresh:")
        if not cache_key or not _is_cache_owner(cache_key, chat_id, user_id, message_id):
            await query.answer("⚠️ 只能操作你自己发起的搜索", show_alert=True)
            return

        cached = search_cache.get(cache_key)
        if not cached:
            await query.answer()
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await _safe_edit_message(query.edit_message_text, expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return

        keyword = cached["keyword"]
        allowed, retry_after = check_search_rate_limit(user_id)
        if not allowed:
            await query.answer(f"⏳ 搜索太频繁了，请在 {retry_after} 秒后再试", show_alert=True)
            return

        await query.answer("正在重新搜索...")
        
        # 执行新搜索 - 使用 query 直接编辑消息
        try:
            # 直接使用已存在的 search_message 进行搜索
            await perform_search_from_callback(
                query,
                context,
                keyword,
                user_id,
                chat_id,
                **cached.get("options", {}),
            )
        except Exception as e:
            logger.error("refresh_search_error", error=str(e))
            safe_error = html.escape(str(e))
            await _safe_edit_message(
                query.edit_message_text,
                f"❌ 重新搜索失败：{safe_error}\n\n请稍后重试",
                parse_mode=ParseMode.HTML
            )
        return
    
    # 处理显示全部
    if data.startswith("all:"):
        cache_key = _parse_cache_key_from_action(data, "all:")
        if not cache_key or not _is_cache_owner(cache_key, chat_id, user_id, message_id):
            await query.answer("⚠️ 只能操作你自己发起的搜索", show_alert=True)
            return

        cached_data = search_cache.get(cache_key)
        if not cached_data:
            await query.answer()
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await _safe_edit_message(query.edit_message_text, expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return
        
        await query.answer("正在整理全部结果...")

        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        user_settings = settings_manager.get_settings(user_id)
        per_type_limit = max(1, min(user_settings.result_limit, settings.max_result_limit))
        formatted_text = pansou_client.format_results(results, keyword, per_type_limit=per_type_limit)
        formatted_text = add_auto_delete_notice(formatted_text, ParseMode.HTML)
        
        formatted_text = ensure_telegram_text(formatted_text, parse_mode=ParseMode.HTML)
        
        await _safe_edit_message(
            query.edit_message_text,
            formatted_text,
            reply_markup=create_all_results_keyboard(cache_key),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        # 重置自动删除计时器
        schedule_message_deletion(chat_id, query.message.message_id)
        return
    
    # 处理返回分类
    if data.startswith("back:"):
        cache_key = _parse_cache_key_from_action(data, "back:")
        if not cache_key or not _is_cache_owner(cache_key, chat_id, user_id, message_id):
            await query.answer("⚠️ 只能操作你自己发起的搜索", show_alert=True)
            return

        cached_data = search_cache.get(cache_key)
        if not cached_data:
            await query.answer()
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await _safe_edit_message(query.edit_message_text, expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return
        
        await query.answer("已返回分类")

        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        overview_text = pansou_client.format_overview(results, keyword)
        overview_text = add_auto_delete_notice(overview_text, ParseMode.HTML)
        type_buttons = pansou_client.get_type_buttons(results)
        keyboard = create_type_keyboard(type_buttons, cache_key)
        
        await _safe_edit_message(
            query.edit_message_text,
            overview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        # 重置自动删除计时器
        schedule_message_deletion(chat_id, query.message.message_id)
        return
    
    # 处理类型选择
    if data.startswith("type:"):
        cache_key, cloud_type, page = _parse_type_callback(data)
        if not cache_key or not cloud_type or page is None:
            await query.answer("❌ 参数错误")
            return

        if not _is_cache_owner(cache_key, chat_id, user_id, message_id):
            await query.answer("⚠️ 只能操作你自己发起的搜索", show_alert=True)
            return

        cached_data = search_cache.get(cache_key)
        if not cached_data:
            await query.answer()
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await _safe_edit_message(query.edit_message_text, expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return

        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        # 检查类型是否存在
        if cloud_type not in results.get("merged_by_type", {}):
            await query.answer("❌ 该类型暂无资源")
            return

        links = results["merged_by_type"][cloud_type]
        user_settings = settings_manager.get_settings(user_id)
        per_page = max(1, min(user_settings.result_limit, settings.max_result_limit))
        total_pages = (len(links) + per_page - 1) // per_page
        
        # 确保页码有效
        page = max(1, min(page, total_pages))
        type_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
        await query.answer(f"{type_name} 第 {page}/{total_pages} 页")
        
        # 格式化该类型的结果
        formatted_text = pansou_client.format_type_results(
            results, keyword, cloud_type, page, per_page
        )
        # 添加自动删除提示
        formatted_text = add_auto_delete_notice(formatted_text, ParseMode.HTML)
        
        # 创建分页键盘
        keyboard = create_pagination_keyboard(cache_key, cloud_type, page, total_pages)
        
        await _safe_edit_message(
            query.edit_message_text,
            formatted_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        # 重置自动删除计时器
        schedule_message_deletion(chat_id, query.message.message_id)
        return


# ============ 错误处理 ============

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    error_text = str(context.error)

    # Ignore no-op edits where Telegram reports identical content.
    if "Message is not modified" in error_text:
        logger.debug("ignored_message_not_modified")
        return

    logger.error("bot_error", error=error_text, update=update)

    if update and update.effective_message:
        try:
            notice_text = add_auto_delete_notice(
                """❌ 发生错误，请稍后重试
如果问题持续存在，请联系管理员""",
                None
            )
            error_msg = await update.effective_message.reply_text(notice_text)
            auto_delete_message(error_msg)
        except Exception:
            pass



# ============ 应用构建 ============

async def _post_init(application) -> None:
    """启动后同步 Telegram 命令菜单。"""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:
        logger.warning("set_bot_commands_failed", error=str(exc))


def create_application():
    """创建并配置 Bot 应用"""
    return build_application(
        BotHandlerSet(
            start=start_command,
            help=help_command,
            types=types_command,
            sources=sources_command,
            plugins=plugins_command,
            channels=channels_command,
            settings=settings_command,
            filter=filter_command,
            reset=reset_command,
            status=status_command,
            refresh=refresh_command,
            update=update_command,
            search=search_command,
            callback=handle_callback,
            private_message=handle_private_message,
            error=error_handler,
        ),
        post_init=_post_init,
    )


async def main() -> None:
    """主入口"""
    import structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logger.info("bot_starting", log_level=settings.log_level)
    
    application = create_application()
    set_bot_application(application)
    
    logger.info("bot_started")
    await application.initialize()
    await application.start()
    
    try:
        bot = application.bot
        user = await bot.get_me()
        logger.info("telegram_api_connected", bot_name=user.first_name, bot_username=user.username)
        print(f"✅ Telegram API 连接成功: {user.first_name} (@{user.username})")
    except Exception as e:
        logger.error("telegram_api_connection_failed", error=str(e))
        print(f"❌ Telegram API 连接失败: {str(e)}")
    
    await application.updater.start_polling(
        drop_pending_updates=True,
        poll_interval=0.5,
        timeout=60,
        bootstrap_retries=3
    )
    
    logger.info("bot_polling_started")
    print("✅ 机器人轮询已启动")
    
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
