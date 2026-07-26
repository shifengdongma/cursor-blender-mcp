# Blender MCP 服务器部署说明（Ubuntu + GPU 实例）

本说明用于在一台 **支持 NVIDIA GPU + 新版 glibc 的 Ubuntu 服务器** 上部署
`Cursor ↔ MCP ↔ Blender` 直连通路。该机器只负责三维建模与视口渲染；当前
CentOS7 + CPU 云主机继续承载 Web + Seedance 调度逻辑。

## 1\. 环境准备（Ubuntu 22.04/24.04 + NVIDIA）

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential git wget curl jq \
  libsm6 libxext6 libxrender-dev

# 安装建议版本的 NVIDIA 驱动与 EGL 依赖（具体版本按云厂商镜像为准）
sudo apt-get install -y nvidia-driver-550
sudo apt-get install -y libnvidia-egl-wayland1 mesa-utils xvfb freeglut3

nvidia-smi
```

安装 Blender（示例使用 snap）：

```bash
sudo snap install blender --classic
```

## 2\. 为 Blender Python 建立虚拟环境

```bash
# 探测 Blender 内部 Python 解释器路径（可在 Ubuntu 机器上执行）
BLENDER_PYTHON=$(/snap/blender/current/blender -b --python-expr "import sys; print(sys.executable)" | grep -v Blender)
echo "Blender Python = $BLENDER_PYTHON"

# 创建独立虚拟环境
$BLENDER_PYTHON -m venv ~/blender_mcp_env
source ~/blender_mcp_env/bin/activate

pip install --upgrade pip
pip install mcp fastmcp numpy opencv-python pydantic
```

## 3\. 部署代码与启动脚本

假设你将当前仓库同步到 Ubuntu 服务器的 `~/blender_mcp` 目录：

```bash
cd ~
git clone <your-repo> blender_mcp   # 或通过 rsync / scp 同步
cd blender_mcp
```

关键文件：

- `blender/server_transport.py`：负责 **stdout 劫持**，把 Blender 内核日志重定向到 stderr。
- `blender/blender_agent.py`：基于 `FastMCP` 的 Blender MCP 服务器。
- `blender/start_blender_mcp.sh`：在 Ubuntu 服务器上启动无头 Blender MCP 的参考脚本。

根据实际路径修改 `start_blender_mcp.sh` 中的变量，然后启动：

```bash
chmod +x blender/start_blender_mcp.sh
BLENDER_BIN=/snap/blender/current/blender \
PROJECT_ROOT=$HOME/blender_mcp \
VENV_DIR=$HOME/blender_mcp_env \
 ./blender/start_blender_mcp.sh
```

建议在 `screen`/`tmux` 或 systemd 服务中长期运行该进程。

## 4\. Cursor 端 MCP 配置（本地开发机）

在本地开发机（运行 Cursor IDE 的机器）中编辑 `~/.cursor/mcp.json`，为 Blender
服务器增加一条配置。注意：当通过 Remote SSH 登录 Ubuntu 服务器时，`command`
和 `env` 路径必须是 **远端绝对路径**。

```json
{
  "mcpServers": {
    "blender-cloud-agent": {
      "command": "/snap/blender/current/blender",
      "args": [
        "--background",
        "--python",
        "/home/ubuntu/blender_mcp/blender/blender_agent.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": "/home/ubuntu/blender_mcp_env/lib/python3.11/site-packages",
        "DISPLAY": ":1",
        "BLENDER_USER_CONFIG": "/tmp/clean_blender_profile"
      }
    }
  }
}
```

要点：

- `PYTHONUNBUFFERED=1`：避免 JSON 流被缓冲导致 Cursor 端无限 Pending。
- `PYTHONPATH`：将虚拟环境的 `site-packages` 注入 Blender 进程。
- `DISPLAY`：如使用 Xvfb，需指向对应的显示号（例如 `:1`）。

## 5\. MCP 工具能力简要说明

`blender/blender_agent.py` 中注册的工具包括：

- `list_scene_objects()`：返回当前场景物体（名称、类型、位置、欧拉角）。
- `run_python_script(code: str)`：在 Blender 进程内执行 Python 代码，适合由 LLM
  生成小段脚本以完成建模/布光任务。
- `robust_operator_execution(object_name: str, operator_code: str)`：通过
  `get_view3d_context()` 伪造 VIEW_3D 上下文，包装必须调用 `bpy.ops` 的高风险操作。
- `capture_viewport(width: int, height: int)`：基于 `gpu.types.GPUOffScreen` 离屏渲染，
  返回 `data:image/jpeg;base64,...` 字符串，便于 Cursor / VLM 做视觉反馈。

在 `.cursorrules` 或项目规则中，建议明确以下原则：

1. 优先使用 `bpy.data` 进行数据驱动操作，只有在布尔、倒角等必须依赖 `bpy.ops`
   的场景才调用 `robust_operator_execution`。
2. 创建或修改复杂场景后，调用 `capture_viewport` 进行快速视觉检查。
3. 对于长时间渲染/模拟任务，将重负载逻辑放入后台线程或分段调用，避免单次 MCP
   工具阻塞过久。

## 6\. 与现有 Web + Seedance 平台的关系

- CentOS7 + CPU 主机：继续负责 Flask Web 前端、Seedance / Atlas Cloud
  视频生成与任务调度。
- Ubuntu + GPU 实例：专职运行 Blender MCP 服务器，提供三维建模、摄像机轨迹、视口
  截图与（可选）本地渲染能力。

后续你可以在 Cursor 会话中同时：

- 调用 Web 平台的 REST API，完成高层“视频任务”调度。
- 通过 MCP 工具直接驱动远端 Blender：生成白模、验证空间约束、捕获视口并反馈给
  Seedance Prompt 构建逻辑，实现“执行–观测–修正”的闭环。 

