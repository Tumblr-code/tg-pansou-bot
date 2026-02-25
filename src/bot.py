#!/usr/bin/env python3
"""
Telegram Bot 主模块 - 支持分类按钮
"""
import asyncio
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from structlog import get_logger

from config import settings
from pansou_client import pansou_client, CLOUD_TYPE_NAMES, CLOUD_TYPE_ICONS
from user_settings import settings_manager, CLOUD_TYPE_NAMES as SETTINGS_CLOUD_NAMES

logger = get_logger()

# 存储搜索结果缓存
search_cache = {}

# 存储需要自动删除的消息
pending_deletions = {}

# Bot 应用实例（在 main() 中设置）
bot_application = None

# 自动删除时间（秒）
AUTO_DELETE_DELAY = 180  # 3分钟

# 线程池用于后台任务
executor = ThreadPoolExecutor(max_workers=4)


# 后台任务队列 - 使用字典优化查找速度
_deletion_tasks = {}
_cleanup_task = None

async def _cleanup_worker():
    """后台清理工作器，批量处理消息删除"""
    global _cleanup_task
    try:
        while _deletion_tasks:
            await asyncio.sleep(5)  # 每5秒检查一次（减少CPU使用）
            now = asyncio.get_event_loop().time()
            
            # 找出需要删除的任务
            to_delete = [
                (chat_id, msg_id) for (chat_id, msg_id), delete_time in _deletion_tasks.items()
                if now >= delete_time
            ]
            
            # 删除消息
            for chat_id, message_id in to_delete:
                try:
                    if bot_application:
                        await bot_application.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:
                    pass
                finally:
                    _deletion_tasks.pop((chat_id, message_id), None)
    finally:
        _cleanup_task = None


def _ensure_cleanup_worker():
    """确保清理工作器在运行"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_worker())


def auto_delete_message(message: Message, delay: int = AUTO_DELETE_DELAY):
    """自动删除消息（超轻量，O(1)操作）"""
    key = (message.chat_id, message.message_id)
    _deletion_tasks[key] = asyncio.get_event_loop().time() + delay
    _ensure_cleanup_worker()


def schedule_message_deletion(chat_id: int, message_id: int, delay: int = AUTO_DELETE_DELAY):
    """安排消息在指定时间后删除（超轻量，O(1)操作）"""
    key = (chat_id, message_id)
    _deletion_tasks[key] = asyncio.get_event_loop().time() + delay
    _ensure_cleanup_worker()


def add_auto_delete_notice(text: str, parse_mode: Optional[str] = None) -> str:
    """在消息中添加自动删除提示（快速版本）"""
    # 使用简单的字符串拼接，避免重复检查
    if parse_mode == ParseMode.HTML:
        return f"{text}\n\n<i>⏰ 此消息将在 3 分钟后自动删除</i>"
    elif parse_mode == ParseMode.MARKDOWN:
        return f"{text}\n\n_⏰ 此消息将在 3 分钟后自动删除_"
    else:
        return f"{text}\n\n⏰ 此消息将在 3 分钟后自动删除"


async def reply_with_auto_delete(
    update: Update,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    **kwargs
) -> Message:
    """发送自动删除的回复消息"""
    # 添加自动删除提示
    text_with_notice = add_auto_delete_notice(text, parse_mode)
    
    message = await update.message.reply_text(
        text_with_notice,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        **kwargs
    )
    auto_delete_message(message)
    return message


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
    
    if is_user_admin:
        # 管理员看到完整功能
        welcome_text = f"""👋 你好，{user.first_name}！

我是 <b>网盘搜索机器人</b>，可以帮你搜索各种网盘资源。

<b>🎯 使用方式：</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令： <code>/search 钢铁侠</code>

<b>✨ 特色功能：</b>
• 📂 搜索结果分类显示，按需查看
• 🔍 支持 12 种网盘类型筛选
• ⚙️ 个人设置持久化
• 🔗 一键复制链接和密码

<b>🔧 管理员命令：</b>
/settings - 查看/修改个人设置
/types - 查看支持的网盘类型
/filter - 设置搜索过滤器
/status - 检查服务状态
/help - 查看详细帮助

👑 <b>你是管理员，拥有所有权限</b>"""
    else:
        # 普通用户只看到简单搜索功能
        welcome_text = f"""👋 你好，{user.first_name}！

我是 <b>网盘搜索机器人</b>，可以帮你搜索各种网盘资源。

<b>🎯 使用方式：</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令： <code>/search 钢铁侠</code>

<b>📁 支持的网盘：</b>
百度、阿里、夸克、天翼、UC、115、PikPak、迅雷、123、磁力、电驴

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

<b>📂 分类查看</b>
搜索后会显示网盘类型按钮，点击即可查看该类型的资源：
🔴 百度网盘 (12)  🟠 夸克网盘 (8)
🔵 阿里云盘 (5)   🧲 磁力链接 (3)

<b>⚙️ 设置管理</b>
• <code>/settings</code> - 查看设置
• <code>/settings types baidu,quark</code> - 设置默认网盘
• <code>/settings limit 15</code> - 设置结果数量
• <code>/settings reset</code> - 重置设置

<b>🔍 过滤器</b>
• <code>/filter add 包含 1080P</code>
• <code>/filter add 排除 预告</code>
• <code>/filter clear</code> - 清除过滤

<b>📁 支持的网盘</b>
百度、阿里、夸克、天翼、UC、115、PikPak、迅雷、123、磁力、电驴"""
    else:
        # 普通用户只看到简单帮助
        help_text = """<b>📖 使用帮助</b>

<b>🔍 基础搜索</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令：<code>/search 钢铁侠</code>

<b>📂 分类查看</b>
搜索后会显示网盘类型按钮，点击即可查看该类型的资源：
🔴 百度网盘 (12)  🟠 夸克网盘 (8)
🔵 阿里云盘 (5)   🧲 磁力链接 (3)

<b>📁 支持的网盘</b>
百度、阿里、夸克、天翼、UC、115、PikPak、迅雷、123、磁力、电驴

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
        types_str = args[1]
        cloud_types = [t.strip() for t in types_str.split(",") if t.strip()]
        
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
    
    if args[0] == "limit" and len(args) > 1:
        try:
            limit = int(args[1])
            if 1 <= limit <= 50:
                settings_manager.update_settings(user_id, result_limit=limit)
                await reply_with_auto_delete(update, f"✅ 结果数量限制已设置为 {limit}")
            else:
                await reply_with_auto_delete(update, "❌ 限制范围：1-50")
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
    user_id = update.effective_user.id
    is_user_admin = is_admin(user_id)
    
    message = await update.message.reply_text("🔄 正在检查服务状态...")
    auto_delete_message(message)
    
    is_healthy = await pansou_client.health_check()
    
    if is_healthy:
        if is_user_admin:
            # 管理员看到完整状态
            user_settings = settings_manager.get_settings(user_id)
            status_text = f"""✅ <b>服务状态正常</b>

🤖 Bot: 运行中
🔍 Pansou API: 正常

<b>您的设置：</b>
📊 结果限制: {user_settings.result_limit}
🔍 搜索来源: {user_settings.source_type}
📁 网盘类型: {len(user_settings.cloud_types)}个
✅ 包含过滤: {len(user_settings.filter_include)}个
❌ 排除过滤: {len(user_settings.filter_exclude)}个

👑 你是管理员"""
        else:
            # 普通用户只看到简单状态
            status_text = """✅ <b>服务状态正常</b>

🤖 Bot: 运行中
🔍 Pansou API: 正常

💡 可以直接发送关键词进行搜索！"""
    else:
        status_text = """⚠️ <b>服务异常</b>

🤖 Bot: 运行中
🔍 Pansou API: 无法连接

请稍后重试..."""
    
    # 添加自动删除提示
    status_text = add_auto_delete_notice(status_text, ParseMode.HTML)
    await message.edit_text(status_text, parse_mode=ParseMode.HTML)


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
    
    keyword = " ".join(args)
    await perform_search(update, context, keyword)


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


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """欢迎新成员加入群组"""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat = update.effective_chat
    
    # 只处理群组和超级群组
    if chat.type not in ["group", "supergroup"]:
        return
    
    for member in update.message.new_chat_members:
        # 跳过机器人自己
        if member.is_bot:
            continue
        
        welcome_text = f"""👋 欢迎 <b>{member.first_name}</b> 加入群组！

我是 <b>网盘搜索机器人</b>，可以帮你搜索各种网盘资源。

<b>🎯 使用方式：</b>
• 直接发送关键词，如：<code>复仇者联盟</code>
• 使用命令：<code>/search 钢铁侠</code>

💡 <b>提示：</b>
• 搜索后会显示网盘类型按钮，点击即可查看结果
• 支持百度、阿里、夸克、天翼等多种网盘
• 所有消息将在 3 分钟后自动清理

/help - 查看详细帮助"""
        
        try:
            message = await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML
            )
            auto_delete_message(message)
        except Exception as e:
            logger.error("welcome_error", error=str(e), user_id=member.id)


# ============ 搜索核心函数 ============

async def perform_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str,
    limit: Optional[int] = None,
    cloud_types: Optional[list] = None,
    source_type: Optional[str] = None
) -> None:
    """执行搜索并显示分类按钮"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_settings = settings_manager.get_settings(user_id)
    
    if limit is None:
        limit = user_settings.result_limit
    limit = min(limit, settings.max_result_limit)
    
    if cloud_types is None:
        cloud_types = user_settings.cloud_types
    
    if source_type is None:
        source_type = user_settings.source_type
    
    filter_config = user_settings.get_filter_config()
    
    # 发送搜索中提示
    search_message = await update.message.reply_text(
        f"🔍 正在搜索：<b>{keyword}</b>...",
        parse_mode=ParseMode.HTML
    )
    
    # 安排搜索结果消息自动删除
    schedule_message_deletion(chat_id, search_message.message_id)
    
    try:
        # 执行搜索
        results = await pansou_client.search(
            keyword=keyword,
            channels=user_settings.channels if user_settings.channels else None,
            plugins=user_settings.plugins if user_settings.plugins else None,
            cloud_types=cloud_types,
            source_type=source_type,
            filter_config=filter_config,
            limit=100  # 获取较多结果用于分类显示
        )
        
        if "error" in results:
            error_text = add_auto_delete_notice(f"❌ {results['error']}", ParseMode.HTML)
            await search_message.edit_text(error_text, parse_mode=ParseMode.HTML)
            # 错误消息也需要自动删除
            schedule_message_deletion(chat_id, search_message.message_id)
            return
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if not merged_by_type or total == 0:
            empty_text = add_auto_delete_notice(f"🔍 未找到与「{keyword}」相关的资源", ParseMode.HTML)
            await search_message.edit_text(empty_text, parse_mode=ParseMode.HTML)
            # 空结果消息也需要自动删除
            schedule_message_deletion(chat_id, search_message.message_id)
            return
        
        # 保存结果到缓存
        cache_key = f"{chat_id}:{user_id}"
        search_cache[cache_key] = {
            "keyword": keyword,
            "results": results,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # 生成概览文本
        overview_text = pansou_client.format_overview(results, keyword)
        # 添加自动删除提示
        overview_text = add_auto_delete_notice(overview_text, ParseMode.HTML)
        
        # 生成类型按钮
        type_buttons = pansou_client.get_type_buttons(results)
        keyboard = create_type_keyboard(type_buttons, cache_key)
        
        await search_message.edit_text(
            overview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        # 更新删除计划（编辑消息后仍保持自动删除）
        schedule_message_deletion(chat_id, search_message.message_id)
        
        logger.info(
            "search_completed",
            keyword=keyword,
            user_id=user_id,
            total=total,
            types=list(merged_by_type.keys())
        )
        
    except Exception as e:
        logger.error("search_error", error=str(e), keyword=keyword)
        await search_message.edit_text(
            f"❌ 搜索出错：{str(e)}\n\n请稍后重试或使用 /status 检查服务状态"
        )
        # 错误消息也需要自动删除
        schedule_message_deletion(chat_id, search_message.message_id)


async def perform_search_from_callback(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str,
    user_id: int,
    chat_id: int,
    limit: Optional[int] = None,
    cloud_types: Optional[list] = None,
    source_type: Optional[str] = None
) -> None:
    """从回调查询执行搜索（用于重新搜索功能）"""
    user_settings = settings_manager.get_settings(user_id)
    message_id = query.message.message_id
    
    if limit is None:
        limit = user_settings.result_limit
    limit = min(limit, settings.max_result_limit)
    
    if cloud_types is None:
        cloud_types = user_settings.cloud_types
    
    if source_type is None:
        source_type = user_settings.source_type
    
    filter_config = user_settings.get_filter_config()
    
    # 更新消息为搜索中状态
    await query.edit_message_text(
        f"🔍 正在搜索：<b>{keyword}</b>...",
        parse_mode=ParseMode.HTML
    )
    
    # 安排消息自动删除
    schedule_message_deletion(chat_id, message_id)
    
    try:
        # 执行搜索
        results = await pansou_client.search(
            keyword=keyword,
            channels=user_settings.channels if user_settings.channels else None,
            plugins=user_settings.plugins if user_settings.plugins else None,
            cloud_types=cloud_types,
            source_type=source_type,
            filter_config=filter_config,
            limit=100
        )
        
        if "error" in results:
            error_text = add_auto_delete_notice(f"❌ {results['error']}", ParseMode.HTML)
            await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, message_id)
            return
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if not merged_by_type or total == 0:
            empty_text = add_auto_delete_notice(f"🔍 未找到与「{keyword}」相关的资源", ParseMode.HTML)
            await query.edit_message_text(empty_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, message_id)
            return
        
        # 保存结果到缓存
        cache_key = f"{chat_id}:{user_id}"
        search_cache[cache_key] = {
            "keyword": keyword,
            "results": results,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # 生成概览文本
        overview_text = pansou_client.format_overview(results, keyword)
        # 添加自动删除提示
        overview_text = add_auto_delete_notice(overview_text, ParseMode.HTML)
        
        # 生成类型按钮
        type_buttons = pansou_client.get_type_buttons(results)
        keyboard = create_type_keyboard(type_buttons, cache_key)
        
        await query.edit_message_text(
            overview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        # 更新删除计划（编辑消息后仍保持自动删除）
        schedule_message_deletion(chat_id, message_id)
        
        logger.info(
            "search_completed",
            keyword=keyword,
            user_id=user_id,
            total=total,
            types=list(merged_by_type.keys())
        )
        
    except Exception as e:
        logger.error("search_error", error=str(e), keyword=keyword)
        error_text = add_auto_delete_notice(
            f"❌ 搜索出错：{str(e)}\n\n请稍后重试或使用 /status 检查服务状态",
            ParseMode.HTML
        )
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        schedule_message_deletion(chat_id, message_id)


def create_type_keyboard(type_buttons: list, cache_key: str, page: int = 1) -> InlineKeyboardMarkup:
    """创建网盘类型选择键盘"""
    buttons = []
    
    # 每行2个按钮
    row = []
    for btn in type_buttons:
        callback_data = f"type:{cache_key}:{btn['type']}:{page}"
        # 确保 callback_data 不超过 64 字节
        if len(callback_data) > 64:
            # 使用简化的 cache_key
            callback_data = f"type:{btn['type']}:{page}"
        
        row.append(InlineKeyboardButton(
            btn["text"],
            callback_data=callback_data
        ))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # 添加操作按钮
    buttons.append([
        InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}"),
        InlineKeyboardButton("📊 显示全部", callback_data=f"all:{cache_key}")
    ])
    
    return InlineKeyboardMarkup(buttons)


def create_pagination_keyboard(
    cache_key: str, 
    cloud_type: str, 
    current_page: int, 
    total_pages: int
) -> InlineKeyboardMarkup:
    """创建分页键盘"""
    buttons = []
    
    # 分页按钮
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                "⬅️ 上一页", 
                callback_data=f"type:{cache_key}:{cloud_type}:{current_page - 1}"
            )
        )
    
    nav_buttons.append(
        InlineKeyboardButton(
            f"{current_page}/{total_pages}", 
            callback_data="noop"
        )
    )
    
    if current_page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                "下一页 ➡️", 
                callback_data=f"type:{cache_key}:{cloud_type}:{current_page + 1}"
            )
        )
    
    buttons.append(nav_buttons)
    
    # 返回和重新搜索按钮
    buttons.append([
        InlineKeyboardButton("🔙 返回分类", callback_data=f"back:{cache_key}"),
        InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}")
    ])
    
    return InlineKeyboardMarkup(buttons)


# ============ 回调处理 ============

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data or data == "noop":
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    cache_key = f"{chat_id}:{user_id}"
    
    # 处理刷新
    if data.startswith("refresh:"):
        parts = data.split(":")
        if len(parts) >= 2:
            # cache_key 格式是 chat_id:user_id，需要重新组合
            old_cache_key = ":".join(parts[1:])
            # 获取之前的搜索关键词
            if old_cache_key in search_cache:
                keyword = search_cache[old_cache_key]["keyword"]
            else:
                keyword = ""
        else:
            keyword = ""
        
        await query.edit_message_text(
            f"🔄 正在重新搜索：<b>{keyword}</b>...",
            parse_mode=ParseMode.HTML
        )
        
        # 执行新搜索 - 使用 query 直接编辑消息
        try:
            # 直接使用已存在的 search_message 进行搜索
            await perform_search_from_callback(query, context, keyword, user_id, chat_id)
        except Exception as e:
            logger.error("refresh_search_error", error=str(e))
            await query.edit_message_text(
                f"❌ 重新搜索失败：{str(e)}\n\n请稍后重试",
                parse_mode=ParseMode.HTML
            )
        return
    
    # 处理显示全部
    if data.startswith("all:"):
        if cache_key not in search_cache:
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await query.edit_message_text(expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return
        
        cached_data = search_cache[cache_key]
        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        formatted_text = pansou_client.format_results(results, keyword)
        # 添加自动删除提示
        formatted_text = add_auto_delete_notice(formatted_text, ParseMode.HTML)
        
        if len(formatted_text) > 4000:
            formatted_text = formatted_text[:3950] + "\n\n...（内容过长已截断）"
        
        buttons = [[
            InlineKeyboardButton("🔙 返回分类", callback_data=f"back:{cache_key}"),
            InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}")
        ]]
        
        await query.edit_message_text(
            formatted_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        # 重置自动删除计时器
        schedule_message_deletion(chat_id, query.message.message_id)
        return
    
    # 处理返回分类
    if data.startswith("back:"):
        if cache_key not in search_cache:
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await query.edit_message_text(expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return
        
        cached_data = search_cache[cache_key]
        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        overview_text = pansou_client.format_overview(results, keyword)
        # 添加自动删除提示
        overview_text = add_auto_delete_notice(overview_text, ParseMode.HTML)
        type_buttons = pansou_client.get_type_buttons(results)
        keyboard = create_type_keyboard(type_buttons, cache_key)
        
        await query.edit_message_text(
            overview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        # 重置自动删除计时器
        schedule_message_deletion(chat_id, query.message.message_id)
        return
    
    # 处理类型选择
    if data.startswith("type:"):
        parts = data.split(":")
        if len(parts) == 3:
            # 简化的格式：type:cloud_type:page
            cloud_type = parts[1]
            page = int(parts[2])
        elif len(parts) >= 5:
            # 完整格式：type:chat_id:user_id:cloud_type:page
            cloud_type = parts[3]
            page = int(parts[4])
        else:
            await query.answer("❌ 参数错误")
            return
        
        if cache_key not in search_cache:
            expired_text = add_auto_delete_notice("⚠️ 搜索结果已过期，请重新搜索", ParseMode.HTML)
            await query.edit_message_text(expired_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, query.message.message_id)
            return
        
        cached_data = search_cache[cache_key]
        results = cached_data["results"]
        keyword = cached_data["keyword"]
        
        # 检查类型是否存在
        if cloud_type not in results.get("merged_by_type", {}):
            await query.answer("❌ 该类型暂无资源")
            return
        
        links = results["merged_by_type"][cloud_type]
        per_page = 5
        total_pages = (len(links) + per_page - 1) // per_page
        
        # 确保页码有效
        page = max(1, min(page, total_pages))
        
        # 格式化该类型的结果
        formatted_text = pansou_client.format_type_results(
            results, keyword, cloud_type, page, per_page
        )
        # 添加自动删除提示
        formatted_text = add_auto_delete_notice(formatted_text, ParseMode.HTML)
        
        # 创建分页键盘
        keyboard = create_pagination_keyboard(cache_key, cloud_type, page, total_pages)
        
        await query.edit_message_text(
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
    logger.error("bot_error", error=str(context.error), update=update)
    
    if update and update.effective_message:
        try:
            error_text = add_auto_delete_notice(
                "❌ 发生错误，请稍后重试\n"
                "如果问题持续存在，请联系管理员",
                None
            )
            error_msg = await update.effective_message.reply_text(error_text)
            auto_delete_message(error_msg)
        except Exception:
            pass


# ============ 应用构建 ============

def create_application() -> Application:
    """创建并配置 Bot 应用"""
    application = (
        Application.builder()
        .token(settings.tg_bot_token)
        .read_timeout(60)   # 给搜索足够时间
        .write_timeout(30)
        .connect_timeout(10)
        .pool_timeout(10)
        .concurrent_updates(True)
        .build()
    )
    
    # 添加命令处理器
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("types", types_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("filter", filter_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("s", search_command, filters=filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP))
    
    # 添加回调处理器
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # 添加私聊消息处理器
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_private_message
        )
    )
    
    # 添加新成员加入处理器（群组欢迎）
    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_member
        )
    )
    
    # 添加错误处理器
    application.add_error_handler(error_handler)
    
    return application


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
    
    global bot_application
    
    logger.info("bot_starting", log_level=settings.log_level)
    
    application = create_application()
    bot_application = application
    
    logger.info("bot_started")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        drop_pending_updates=True,
        poll_interval=0.5,  # 更快的轮询间隔
        timeout=10,         # 请求超时
        bootstrap_retries=3
    )
    
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
