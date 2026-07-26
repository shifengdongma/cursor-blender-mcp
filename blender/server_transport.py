"""
Blender MCP 传输层：标准输出流劫持（FD Hijacking）。

设计目标：
- Blender 内核（C/C++）的大量日志全部重定向到 stderr，避免污染 MCP JSON 流。
- 为 MCP server 保留一个“干净”的 stdout 管道（mcp_pipe_fd）专门发送 JSON-RPC。

注意：
- 只有在真正作为 MCP 服务器从 Cursor 启动时才需要启用。
- 需要结合自定义 Transport 或在 MCP SDK 中接管“写出”逻辑，将 JSON 写入 mcp_pipe_fd。
"""

from __future__ import absolute_import

import os
import sys


class StdoutHijacker(object):
    def __init__(self):
        self.original_stdout_fd = None
        self.mcp_pipe_fd = None

    def hijack(self):
        """
        将底层 Stdout(FD 1) 重定向到 Stderr(FD 2)，
        同时复制出一个仅供 MCP 使用的干净管道。
        """
        # 1) 复制当前 stdout FD —— 这个句柄指向“原始”的 stdout 管道
        self.mcp_pipe_fd = os.dup(sys.stdout.fileno())

        # 2) 获取 stderr FD
        stderr_fd = sys.stderr.fileno()

        # 3) 确保现有缓冲区写出
        sys.stdout.flush()

        # 4) 将 FD 1 物理指向 FD 2：之后一切写往 stdout 的 C 级日志都会流向 stderr
        os.dup2(stderr_fd, sys.stdout.fileno())

    def send_mcp_message(self, message):
        """
        通过独立的 mcp_pipe_fd 发送纯净 JSON 文本。
        实际集成时，可在 MCP SDK/Transport 中调用该方法写出响应。
        """
        if self.mcp_pipe_fd is None:
            raise RuntimeError("Stdout hijack not initialized.")
        payload = message.encode("utf-8")
        os.write(self.mcp_pipe_fd, payload)


# 全局单例
hijacker = StdoutHijacker()

