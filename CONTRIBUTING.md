# 贡献 / Contributing

本次发行以已核验的在线源码为准。先阅读 README 与 `docs/PRODUCTION_SOURCE.json`；新增业务改动须单独说明，不能静默改变基线或用真实客户请求测试。保持历史记录，使用短期 `codex/` 分支和 PR，精确提交的 CI 通过并完成审查后合入 main；随后删除已合并源分支。不要修改其他任务 worktree 或未合并独有分支。

This release is based on verified deployed source. Read the README and source manifest first. Scope behavioral changes separately; never silently alter the baseline or test with real customer requests. Use a short-lived `codex/` branch and PR, review the exact head and pass its required checks before merging, then remove the merged source branch. Preserve history, unique unmerged work and other worktrees.

运行 README 中的来源校验、完整测试和构建命令。修改中英文核心文档时同时更新两种语言。Release 需要可追踪提交、SHA256 与来源清单；GitHub 发布不代表生产已部署。

Run the README's provenance checks, full tests and build commands. Keep both core documentation languages aligned. A release needs a traceable revision, SHA256 sums and provenance; GitHub publication is not production deployment.
