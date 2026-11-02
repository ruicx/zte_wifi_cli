# zte-wifi-cli

[English](README.md)

通过 Web 控制台 API 命令行控制 ZTE 随身 WiFi（U30Air，固件
F50ProV1.0.0B28）——无需浏览器。

逆向协议要点（均已实测验证）：

- **登录**：挑战响应 `SHA256_upper(SHA256_upper(pw) + LD)`，`LD` 挑战值来自
  `cmd=LD`；会话由 `JSESSIONID` cookie 保持。
- **写命令带签名**：`AD = SHA256_upper(SHA256_upper(rd0 + rd1) + RD)`，其中
  `rd0`/`rd1` 是固件版本字符串，`RD` 是每次请求的挑战值。
- **WiFi 开关**：`switchWiFiModule` 的 `SwitchOption` —— **语义相反**：
  `"0"` 开启无线电，`"1"` 关闭。

## 安装

```console
uv sync
uv run zte auth        # 将 Web 控制台密码存入 Windows 凭据管理器
```

### 密码存储

`zte auth` 会要求输入两次 Web 控制台密码（隐藏输入），并以通用凭据
（`zte-wifi-cli` / `web-admin`）的形式存入 **Windows 凭据管理器**。注意：

- 隐藏输入直接读取控制台——无法通过管道或脚本喂数据，必须手动交互输入。
- 验证位置：**控制面板 → 用户账户 → 凭据管理器 → Windows 凭据 →
  普通凭据**，能看到 `zte-wifi-cli/web-admin`（Windows 会遮盖密码值，
  在那里只能删除、不能查看）。
- 修改密码（如在 Web 控制台改过之后）：重新运行 `uv run zte auth`，
  会覆盖已存条目。
- 删除：在凭据管理器界面删除该条目，或运行
  `uv run python -c "import keyring; keyring.delete_password('zte-wifi-cli', 'web-admin')"`。

## 使用

```console
uv run zte status              # 运营商 / 信号 / 连接 / 速率 / WiFi / SIM 总览
uv run zte wifi status
uv run zte wifi on
uv run zte wifi off            # 询问确认；--force 跳过
uv run zte sim status
uv run zte sim switch 2        # 阻塞等待 modem 重新驻网（最长约 2 分钟）
uv run zte net status
uv run zte net mode 4g         # auto | nsa | sa | 4g3g | 4g | 3g
```

所有命令均支持 `--json`（机器可读输出）以及 `--host` / `ZTE_HOST`
（覆盖默认地址 `192.168.0.1`）。

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 设备错误 / 状态变更超时 |
| 2 | 凭据错误（请运行 `zte auth`） |
| 3 | 设备不可达 |

> 注：`zte sim switch` 依据设备 Web 前端提取的协议实现（`SET_SIM_SLOT` +
> `switch_sim_result` 轮询），但**尚未实测**——开发时卡槽 2 没有 SIM 卡。
> WiFi 开关、网络模式和所有状态读取均已实测验证。

## Agent Skill

`skill/zte-wifi/SKILL.md` 是教 agent 驱动本 CLI 的技能文件（英文）。
安装到所有工作区：

```console
xcopy /E /I /Y skill\zte-wifi "%USERPROFILE%\.zcode\skills\zte-wifi"
```

## 开发

```console
uv run pre-commit install   # 一次性：启用 git 钩子（ruff + ty + 卫生检查）
uv run ruff check           # 代码检查（必须通过）
uv run ty check             # 静态类型检查（必须通过）
```

项目结构：`src/zte_wifi_cli/` —— `client.py`（协议）、`cli.py`（click
命令）、`cred.py`（keyring）、`crypto.py`（设备哈希）。
