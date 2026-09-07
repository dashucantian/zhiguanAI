# 坑 006：GitHub HTTPS(443) 被阻断，git push 超时——改走 SSH over 443

## 现象（用户视角，原话）

- "https://github.com/dashucantian/zhiguanAI.git 显示 404 啊！"
- "zhiguanAI 仓库好了，本地 git 可以用了吗？"

AI 侧观察到的错误：
```
fatal: unable to access 'https://github.com/.../zhiguanAI.git/':
Recv failure: Connection was reset
fatal: unable to access '...': Failed to connect to github.com:443 after 21052 ms
```
push 命令挂起直至超时（120 秒），重试三次均失败。

## 根因（两个独立问题叠加，容易混为一谈）

**问题一：404 —— 远程仓库根本没创建。**
上一轮只执行了 `git remote add origin <url>`（登记远程地址），但既没在 GitHub 上建仓库、也没 push。`remote add` 只是写本地配置，不会在远端创建任何东西。所以访问那个 URL 就是 404。

**问题二：push 超时 —— 本机到 github.com:443 被阻断。**
这是国内网络访问 GitHub 的常见情况。诊断证据：

| 测试项 | 结果 |
|--------|------|
| DNS 解析 github.com | 正常（20.205.243.166） |
| github.com:443 (HTTPS) | **连不上**（TcpTestSucceeded=False） |
| www.baidu.com:443（对照） | 正常 |
| github.com:22 (SSH) | 通 |
| ssh.github.com:443 (SSH over 443) | 通 |
| git 认证（credential.helper） | 已就绪（manager） |
| 本地仓库 | 已初始化，1 个提交在 master |

DNS 能解析、国内站点 443 通、唯独 GitHub 443 不通 → 不是本机网络坏了，是到 GitHub 的 HTTPS 通道被阻断。**认证和 git 配置都没问题，纯网络层。**

## 解法

改走 SSH 协议，并让 SSH 走 443 端口（ssh.github.com:443 实测通，即使将来 22 也被墙仍能走）：

1. **生成 SSH 密钥**（ed25519，空密码便于自动化）：
   ```bash
   ssh-keygen -t ed25519 -C "your_email" -f ~/.ssh/id_ed25519 -N ""
   ```
   注意：在 PowerShell 里直接跑 `ssh-keygen -N ""` 会因引号被吞而失败，改用 bash 脚本文件执行（见坑 005）。

2. **配置 SSH 走 443**，写入 `~/.ssh/config`：
   ```
   Host github.com
     HostName ssh.github.com
     Port 443
     User git
   ```

3. **把公钥加到 GitHub**：https://github.com/settings/ssh/new （这一步必须用户本人做，AI 无法代登录）

4. **远程地址从 HTTPS 改为 SSH**：
   ```bash
   git remote set-url origin git@github.com:<user>/<repo>.git
   ```

5. **push**（首次用 accept-new 自动信任主机指纹）：
   ```bash
   GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git push -u origin master
   ```

## 排障顺序（可复用）

git push 超时/连接被重置，**先分清是"远程没建"还是"网络不通"**：

1. 先 `git ls-remote origin`：若报 404/repository not found → 远程仓库没建，去 GitHub 建空仓库（**不要**勾 README/.gitignore/license，否则与本地冲突）
2. 若报 Connection reset / Could not connect:443 → 测端口连通性：
   - `Test-NetConnection github.com -Port 443`（HTTPS）
   - `Test-NetConnection github.com -Port 22`（SSH）
   - `Test-NetConnection ssh.github.com -Port 443`（SSH over 443）
   - 用一个国内站点（如 baidu:443）作对照，确认是不是本机整体断网
3. 443 不通但 SSH 通 → 改 SSH 协议（本坑解法）
4. 全都不通 → 本机网络/防火墙问题，或需要代理

**不要一上来就重装 git 或改认证**——认证（credential.helper=manager）和 git 本身大概率没问题。

## 教训

1. **`git remote add` ≠ 创建远程仓库**。它只写本地配置。远程仓库必须先在 GitHub 上建好，push 才有目标。这是新手最容易误解的一步。
2. **国内访问 GitHub，HTTPS(443) 经常不稳定，SSH 更可靠**。而且要让 SSH 也走 443（ssh.github.com:443），因为 22 端口在某些网络下也会被阻断。一次配好，长期受益。
3. **诊断网络问题要有对照组**。测 GitHub 443 不通时，同时测百度 443——通了就说明不是本机断网，而是到 GitHub 的特定通道问题。没有对照，容易误判成"我网断了"或"git 坏了"。
4. **push 超时要设 GIT_TERMINAL_PROMPT=0**，否则 git 会挂在等待输入凭据上，表现为"卡死"而非"报错"，更难排查。

## 关联

- 工作日志 005（2026-09-06）
- 看板 ZG-036（N8 GitHub 开源仓建立）
- 坑 005（PowerShell 引号吞噬——生成密钥时同样踩到）
- 相关文件：`~/.ssh/config`、`~/.ssh/id_ed25519`、`.git/config`（remote origin）

---

## English Summary

**Symptom:** `https://github.com/<user>/<repo>` returns 404; `git push` hangs or fails with `Connection was reset` / `Could not connect to github.com:443`.

**Root cause (two stacked issues):**
1. The remote repo had never actually been created—`git remote add` only writes local config; it does not create anything on GitHub.
2. GitHub's HTTPS port 443 is intermittently blocked on this network (China), while domestic sites' 443 work fine. DNS resolves, git credentials are ready—purely a transport-path problem.

**Diagnosis table:** github.com:443 ❌ | github.com:22 ✅ | ssh.github.com:443 ✅ | baidu.com:443 ✅ (control group). Without the control group you'd wrongly conclude "my internet is broken."

**Solution:** switch remote to SSH, routed over port 443 for durability:
1. `ssh-keygen -t ed25519` (via a bash script file—PowerShell eats `-N ""`, see Pitfall 005)
2. `~/.ssh/config`: `Host github.com → HostName ssh.github.com, Port 443, User git`
3. User adds the public key at github.com/settings/ssh/new (only the human can do this)
4. `git remote set-url origin git@github.com:<user>/<repo>.git`
5. `GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git push -u origin master`

**Reusable order:** push fails → `git ls-remote origin` first: "repository not found" → create the empty remote repo (uncheck README/.gitignore/license to avoid conflicts); connection reset → port-test GitHub 443/22 and ssh.github.com:443 with a domestic-site control; SSH reachable → switch protocol. Don't reinstall git or touch credentials—those were never the problem.

**Lessons:** (1) `git remote add` ≠ repo created. (2) From China, SSH-over-443 is more durable than HTTPS or bare port 22. (3) Always network-diagnose with a control group. (4) Set `GIT_TERMINAL_PROMPT=0` so auth hangs surface as errors, not infinite hangs.
