# 坑 005：PowerShell 5.1 引号吞噬，导致 lark-cli 参数传递失败

## 现象

调用飞书多维表格 API 时，命令行报错：

```
lark-cli base +record-batch-create --base-token ... --table-id ... --records '[{"fields":{"任务名":"ZG-001 初始化项目仓库"}}]'
```

报错信息：`JSON parse error at position 1: expected '{' but got '['`

看起来是 JSON 格式错误，但实际上 JSON 本身没问题——问题出在 PowerShell 5.1 对引号的处理。

## 根因

PowerShell 5.1 在将参数传递给外部命令（如 Node.js 编写的 lark-cli）时，会**吞噬外层引号**，导致：

- 你写的：`'[{"fields":...}]'`（单引号包裹的 JSON 数组）
- PowerShell 传给 lark-cli 的：`[{fields:...}]`（单引号被去掉，JSON 键名的双引号也被去掉）
- lark-cli 收到的：非法 JSON

这是 Windows PowerShell 5.1 的已知行为，与 lark-cli 本身无关。

## 解法

**用文件传递 JSON 参数**，避免命令行引号问题：

1. 将 JSON 写入临时文件：
   ```powershell
   $json = '[{"fields":{"任务名":"ZG-001"}}]'
   $json | Out-File -FilePath "$env:TEMP\zg_payload.json" -Encoding utf8
   ```

2. 用 `@` 符号引用文件：
   ```powershell
   lark-cli base +record-batch-create --base-token ... --table-id ... --records "@$env:TEMP\zg_payload.json"
   ```

3. 用完后删除临时文件：
   ```powershell
   Remove-Item "$env:TEMP\zg_payload.json"
   ```

## 排障顺序（可复用）

调用外部 CLI 工具传 JSON 参数时：

1. 先检查 JSON 本身是否合法（用 `ConvertFrom-Json` 测试）
2. 如果 JSON 合法但仍报错，**怀疑 PowerShell 引号问题**
3. 改用文件传递（`@文件路径`）
4. 验证文件内容是否正确（用 `Get-Content` 查看）

## 教训

**Windows 环境下，命令行参数传递复杂 JSON 时，优先用文件而非内联字符串。** 这是 PowerShell 5.1 的固有限制，不是 bug，但确实容易踩坑。文件传递虽然多一步，但更可靠、更易调试（可以直接查看文件内容）。

这个坑不只影响 lark-cli，任何需要传 JSON 的外部命令都可能遇到。记住这个模式：`Out-File` → `@文件路径` → `Remove-Item`。

## 关联

- 工作日志 005（2026-09-06）§2.6 第四轮排障
- 相关文件：`console_server.py`（飞书 API 调用部分）

---

## English Summary

**Symptom:** Passing inline JSON to an external CLI via PowerShell 5.1 silently corrupts it—double quotes disappear, the tool receives `<invalid_json>` or splits the argument at every space.

**Root cause:** PowerShell 5.1's native-command argument parsing strips/reinterprets quotes and backticks. Not a bug in the CLI—it's a shell limitation.

**Solution pattern:**
1. Write JSON to a temp file (UTF-8), pass via the tool's file/stdin interface (`@file` syntax)
2. For unavoidable inline JSON: escape quotes as `\"`, generate backticks via `chr(96)`, avoid spaces (compact JSON, space-free format strings)
3. Delete temp files afterwards

**Reusable order:** external CLI rejects your JSON → validate the JSON itself (`ConvertFrom-Json`) → if valid, suspect PowerShell quoting → switch to file passing → verify file contents.

**Lesson:** On Windows, pass complex JSON via files, not inline strings. The pattern `Out-File → @filepath → Remove-Item` applies to any CLI (lark-cli here, ssh-keygen's `-N ""` later hit the same wall).
