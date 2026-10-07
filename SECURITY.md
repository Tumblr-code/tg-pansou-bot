# 安全报告 / Security reporting

请通过仓库 GitHub 的私密漏洞报告功能（若已启用）联系维护者；否则先提交不含漏洞细节或秘密的 issue 请求私密沟通渠道。不要在公开 issue、PR、日志或截图中上传真实 Token、环境文件、用户设置、缓存内容、数据库或可利用的生产细节。

Use GitHub private vulnerability reporting when enabled. Otherwise open a minimal issue requesting a private contact channel without disclosing exploit details or secrets. Never publish real tokens, environment files, user settings, cache contents, databases or actionable production details.

复现应使用隔离环境和模拟数据；不向真实用户发消息，不修改线上状态。报告受影响版本、最小复现、影响和脱敏证据。若凭据已泄露，由所有者轮换；删除分支不等于清除历史秘密。

Reproduce with isolated services and synthetic data, without messaging real users or changing production. Include the affected revision, minimal reproduction, impact and redacted evidence. Owners must rotate exposed credentials; branch deletion does not erase secrets from history.
