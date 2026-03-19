"""
企业微信客服适配层
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import struct
import time
from collections import OrderedDict
from typing import Any, Optional
from xml.etree import ElementTree as ET

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from structlog import get_logger

from config import settings
from pansou_client import CLOUD_TYPE_NAMES, pansou_client

logger = get_logger()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _normalize_multiline_text(value: Any) -> str:
    if value is None:
        return ""

    lines = []
    for raw_line in str(value).splitlines():
        lines.append(" ".join(raw_line.split()).strip())

    normalized = "\n".join(line for line in lines if line)
    return normalized.strip()


def _parse_xml_payload(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    payload: dict[str, Any] = {}

    for child in root:
        if list(child):
            nested: dict[str, Any] = {}
            for grandchild in child:
                nested[grandchild.tag] = (grandchild.text or "").strip()
            payload[child.tag] = nested
            continue

        payload[child.tag] = (child.text or "").strip()

    return payload


class WeComCrypto:
    """企业微信回调加解密。"""

    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        self.token = token
        self.receive_id = receive_id
        self.aes_key = base64.b64decode(f"{encoding_aes_key}=")
        self.iv = self.aes_key[:16]

    def _signature(self, timestamp: str, nonce: str, encrypted: str) -> str:
        raw = "".join(sorted([self.token, timestamp, nonce, encrypted]))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> None:
        expected = self._signature(timestamp, nonce, encrypted)
        if expected != msg_signature:
            raise ValueError("企业微信签名校验失败")

    @staticmethod
    def _pkcs7_unpad(data: bytes) -> bytes:
        if not data:
            raise ValueError("企业微信消息体为空")

        pad_len = data[-1]
        if pad_len < 1 or pad_len > 32:
            raise ValueError("企业微信填充长度非法")

        if data[-pad_len:] != bytes([pad_len]) * pad_len:
            raise ValueError("企业微信填充内容非法")

        return data[:-pad_len]

    def decrypt(self, encrypted: str) -> str:
        encrypted_bytes = base64.b64decode(encrypted)
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(encrypted_bytes) + decryptor.finalize()
        plaintext = self._pkcs7_unpad(padded)

        if len(plaintext) < 20:
            raise ValueError("企业微信消息体长度不足")

        xml_length = struct.unpack("!I", plaintext[16:20])[0]
        xml_end = 20 + xml_length
        xml_text = plaintext[20:xml_end].decode("utf-8")
        receive_id = plaintext[xml_end:].decode("utf-8")

        if self.receive_id and receive_id != self.receive_id:
            raise ValueError("企业微信接收方标识不匹配")

        return xml_text

    def verify_and_decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> str:
        self.verify_signature(msg_signature, timestamp, nonce, encrypted)
        return self.decrypt(encrypted)


class WeComClient:
    """企业微信客服 API 客户端。"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._token_lock = asyncio.Lock()
        self._access_token: Optional[str] = None
        self._access_token_expires_at = 0.0
        self._crypto: Optional[WeComCrypto] = None
        self._cursor_by_kfid: dict[str, str] = {}
        self._sync_locks: dict[str, asyncio.Lock] = {}
        self._processed_msgids: OrderedDict[str, float] = OrderedDict()
        self._processed_msg_ttl = 24 * 60 * 60
        self._processed_msg_cap = 4096
        self._startup_time = int(time.time())
        self._bootstrap_recent_seconds = 180

    def has_api_credentials(self) -> bool:
        return bool(settings.wecom_corp_id and settings.wecom_secret)

    def has_callback_credentials(self) -> bool:
        return bool(settings.wecom_corp_id and settings.wecom_token and settings.wecom_encoding_aes_key)

    @property
    def crypto(self) -> WeComCrypto:
        if not self.has_callback_credentials():
            raise RuntimeError("企业微信回调参数未完整配置")

        if self._crypto is None:
            self._crypto = WeComCrypto(
                token=settings.wecom_token or "",
                encoding_aes_key=settings.wecom_encoding_aes_key or "",
                receive_id=settings.wecom_corp_id or "",
            )
        return self._crypto

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._client_lock:
                if self._client is None or self._client.is_closed:
                    proxy = None
                    proxies = settings.get_proxies()
                    if proxies:
                        proxy = proxies.get("https://") or proxies.get("http://")

                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0),
                        proxy=proxy,
                        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0),
                        http2=True,
                    )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_access_token(self, force_refresh: bool = False) -> str:
        if not self.has_api_credentials():
            raise RuntimeError("企业微信 API 参数未完整配置")

        now = time.monotonic()
        if not force_refresh and self._access_token and now < self._access_token_expires_at:
            return self._access_token

        async with self._token_lock:
            now = time.monotonic()
            if not force_refresh and self._access_token and now < self._access_token_expires_at:
                return self._access_token

            client = await self._get_client()
            response = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={
                    "corpid": settings.wecom_corp_id,
                    "corpsecret": settings.wecom_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("errcode") != 0:
                raise RuntimeError(f"企业微信获取 access_token 失败: {data.get('errmsg', 'unknown error')}")

            expires_in = int(data.get("expires_in", 7200))
            self._access_token = str(data["access_token"])
            self._access_token_expires_at = time.monotonic() + max(expires_in - 120, 60)
            return self._access_token

    async def _request(self, method: str, path: str, retry_on_token_error: bool = True, **kwargs: Any) -> dict[str, Any]:
        access_token = await self.get_access_token(force_refresh=False)
        client = await self._get_client()
        response = await client.request(
            method,
            f"https://qyapi.weixin.qq.com{path}",
            params={"access_token": access_token},
            **kwargs,
        )
        response.raise_for_status()
        data = response.json()

        errcode = int(data.get("errcode", 0))
        if errcode == 0:
            return data

        if retry_on_token_error and errcode in {40014, 42001}:
            logger.warning("wecom_access_token_refresh", errcode=errcode)
            await self.get_access_token(force_refresh=True)
            return await self._request(method, path, retry_on_token_error=False, **kwargs)

        raise RuntimeError(f"企业微信接口调用失败: {data.get('errmsg', 'unknown error')} ({errcode})")

    async def list_accounts(self) -> list[dict[str, Any]]:
        if not self.has_api_credentials():
            raise RuntimeError("企业微信 API 参数未完整配置")

        accounts: list[dict[str, Any]] = []
        offset = 0
        page_size = 100

        while True:
            data = await self._request(
                "GET",
                "/cgi-bin/kf/account/list",
                json={"offset": offset, "limit": page_size},
            )
            batch = data.get("account_list") or []
            for account in batch:
                accounts.append(
                    {
                        "open_kfid": _normalize_text(account.get("open_kfid")),
                        "name": _normalize_text(account.get("name")),
                        "avatar": _normalize_text(account.get("avatar")),
                    }
                )

            if len(batch) < page_size:
                break

            offset += len(batch)

        return accounts

    async def sync_messages(self, sync_token: str, open_kfid: str, cursor: str = "") -> dict[str, Any]:
        return await self._request(
            "POST",
            "/cgi-bin/kf/sync_msg",
            json={
                "cursor": cursor,
                "token": sync_token,
                "limit": 1000,
                "voice_format": 0,
                "open_kfid": open_kfid,
            },
        )

    async def send_text_message(self, touser: str, open_kfid: str, content: str) -> dict[str, Any]:
        text = self._trim_utf8(_normalize_multiline_text(content), max_bytes=1900)
        if not text:
            raise RuntimeError("企业微信回复内容为空")

        return await self._request(
            "POST",
            "/cgi-bin/kf/send_msg",
            json={
                "touser": touser,
                "open_kfid": open_kfid,
                "msgid": f"pansou_{int(time.time() * 1000)}_{secrets.token_hex(4)}",
                "msgtype": "text",
                "text": {"content": text},
            },
        )

    def verify_and_decrypt_echostr(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        return self.crypto.verify_and_decrypt(msg_signature, timestamp, nonce, echostr)

    def parse_callback_envelope(self, xml_text: str) -> dict[str, Any]:
        payload = _parse_xml_payload(xml_text)
        if "Encrypt" not in payload:
            raise ValueError("企业微信回调缺少 Encrypt 字段")
        return payload

    def verify_and_decrypt_callback(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypted: str,
    ) -> dict[str, Any]:
        decrypted_xml = self.crypto.verify_and_decrypt(msg_signature, timestamp, nonce, encrypted)
        payload = _parse_xml_payload(decrypted_xml)
        payload["_raw_xml"] = decrypted_xml
        return payload

    def _get_sync_lock(self, open_kfid: str) -> asyncio.Lock:
        if open_kfid not in self._sync_locks:
            self._sync_locks[open_kfid] = asyncio.Lock()
        return self._sync_locks[open_kfid]

    def _purge_processed_msgids(self) -> None:
        now = time.monotonic()
        while self._processed_msgids:
            msgid, expires_at = next(iter(self._processed_msgids.items()))
            if expires_at > now:
                break
            self._processed_msgids.pop(msgid, None)

        while len(self._processed_msgids) > self._processed_msg_cap:
            self._processed_msgids.popitem(last=False)

    def _is_processed(self, msgid: str) -> bool:
        self._purge_processed_msgids()
        return msgid in self._processed_msgids

    def _mark_processed(self, msgid: str) -> None:
        self._purge_processed_msgids()
        self._processed_msgids[msgid] = time.monotonic() + self._processed_msg_ttl
        self._processed_msgids.move_to_end(msgid)

    @staticmethod
    def _trim_utf8(text: str, max_bytes: int) -> str:
        data = text.encode("utf-8")
        if len(data) <= max_bytes:
            return text

        trimmed = text
        while trimmed and len(trimmed.encode("utf-8")) > max_bytes:
            trimmed = trimmed[:-1]
        return trimmed

    def _flatten_items(self, results: dict[str, Any], item_limit: int) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        merged_by_type = results.get("merged_by_type", {})

        for cloud_type, links in merged_by_type.items():
            cloud_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
            for link in links:
                items.append(
                    {
                        "cloud_type": cloud_type,
                        "cloud_name": cloud_name,
                        "note": _normalize_text(link.get("note")) or "未命名资源",
                        "url": _normalize_text(link.get("url")),
                        "password": _normalize_text(link.get("password")),
                    }
                )
                if len(items) >= item_limit:
                    return items

        return items

    def _format_search_reply(self, keyword: str, results: dict[str, Any]) -> str:
        keyword_text = _normalize_text(keyword)
        if "error" in results:
            return f"搜索「{keyword_text}」失败：{_normalize_text(results['error'])}"

        total = int(results.get("total", 0) or 0)
        if total <= 0:
            return f"没有找到与「{keyword_text}」相关的资源，请换个关键词试试。"

        item_limit = max(1, min(settings.wecom_search_limit, 5))
        items = self._flatten_items(results, item_limit=item_limit)
        lines = [f"「{keyword_text}」共找到 {total} 条资源，先给你 {len(items)} 条：", ""]

        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. [{item['cloud_name']}] {item['note']}")
            lines.append(item["url"])
            if item["password"]:
                lines.append(f"密码：{item['password']}")
            lines.append("")

        if total > len(items):
            lines.append("结果较多，回复更具体的关键词可以更快定位。")

        return self._trim_utf8("\n".join(lines).strip(), max_bytes=1900)

    @staticmethod
    def _is_customer_text_message(message: dict[str, Any]) -> bool:
        msgtype = _normalize_text(message.get("msgtype")).lower()
        if msgtype != "text":
            return False

        origin = message.get("origin")
        try:
            origin_value = int(origin)
        except (TypeError, ValueError):
            return False

        # 企业微信客服 sync_msg 官方示例中 origin=3 为客户发来的消息，这里按该约定过滤，避免回声循环。
        return origin_value == 3

    async def _handle_synced_message(
        self,
        message: dict[str, Any],
        bootstrap_mode: bool,
        open_kfid: str,
    ) -> None:
        msgid = _normalize_text(message.get("msgid"))
        if not msgid or self._is_processed(msgid):
            return

        self._mark_processed(msgid)

        if not self._is_customer_text_message(message):
            return

        send_time = int(message.get("send_time", 0) or 0)
        if bootstrap_mode and send_time and send_time < self._startup_time - self._bootstrap_recent_seconds:
            logger.info("wecom_skip_old_message", msgid=msgid, open_kfid=open_kfid, send_time=send_time)
            return

        external_userid = _normalize_text(message.get("external_userid"))
        if not external_userid:
            logger.warning("wecom_missing_external_userid", msgid=msgid, open_kfid=open_kfid)
            return

        text_payload = message.get("text") or {}
        keyword = _normalize_text(text_payload.get("content"))
        if not keyword:
            return

        logger.info("wecom_search_request", open_kfid=open_kfid, external_userid=external_userid, keyword=keyword)
        results = await pansou_client.search(keyword=keyword, limit=max(settings.wecom_search_limit, 5))
        reply_text = self._format_search_reply(keyword, results)
        await self.send_text_message(touser=external_userid, open_kfid=open_kfid, content=reply_text)

    async def handle_callback(self, callback_payload: dict[str, Any]) -> None:
        event = _normalize_text(callback_payload.get("Event"))
        if event != "kf_msg_or_event":
            logger.info("wecom_callback_ignored", event=event or "unknown")
            return

        sync_token = _normalize_text(callback_payload.get("Token"))
        open_kfid = _normalize_text(callback_payload.get("OpenKfId")) or _normalize_text(settings.wecom_open_kfid)
        if not sync_token or not open_kfid:
            logger.warning("wecom_callback_missing_fields", has_token=bool(sync_token), has_open_kfid=bool(open_kfid))
            return

        lock = self._get_sync_lock(open_kfid)
        async with lock:
            cursor = self._cursor_by_kfid.get(open_kfid, "")
            bootstrap_mode = open_kfid not in self._cursor_by_kfid

            while True:
                payload = await self.sync_messages(sync_token=sync_token, open_kfid=open_kfid, cursor=cursor)
                msg_list = payload.get("msg_list") or []
                next_cursor = _normalize_text(payload.get("next_cursor")) or cursor

                for message in msg_list:
                    try:
                        await self._handle_synced_message(message, bootstrap_mode=bootstrap_mode, open_kfid=open_kfid)
                    except Exception as exc:
                        logger.exception("wecom_message_handle_failed", error=str(exc), message=message)

                if payload.get("has_more") and next_cursor == cursor:
                    logger.warning("wecom_sync_cursor_stalled", open_kfid=open_kfid, cursor=cursor)
                    break

                cursor = next_cursor
                if not payload.get("has_more") or not next_cursor:
                    break

            if cursor:
                self._cursor_by_kfid[open_kfid] = cursor


wecom_client = WeComClient()
