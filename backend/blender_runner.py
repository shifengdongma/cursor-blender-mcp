import json
import logging
import os
import subprocess


# 配置日志
logger = logging.getLogger(__name__)

# Blender 执行超时时间（秒）
BLENDER_TIMEOUT = 300


class BlenderRunnerError(RuntimeError):
    pass


def run_blender_export(blender_bin, spec_path, out_dir, timeout=None):
    """
    调用无头 Blender 执行批处理脚本，导出 glb、相机轨迹等产物。

    Args:
        blender_bin: Blender 可执行文件路径
        spec_path: 场景规格 JSON 文件路径
        out_dir: 输出目录
        timeout: 执行超时时间（秒），默认使用 BLENDER_TIMEOUT

    Returns:
        dict: artifacts.json 内容

    Raises:
        BlenderRunnerError: Blender 执行失败时抛出
    """
    if timeout is None:
        timeout = BLENDER_TIMEOUT

    os.makedirs(out_dir, exist_ok=True)

    script_path = os.path.join(os.path.dirname(__file__), "..", "blender", "blender_batch.py")
    script_path = os.path.abspath(script_path)

    cmd = [
        blender_bin,
        "-b",
        "-P",
        script_path,
        "--",
        "--spec",
        spec_path,
        "--out",
        out_dir,
    ]

    logger.info("Running Blender export: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error("Blender execution failed: %s", error_msg)
            raise BlenderRunnerError(
                "Blender 执行失败 (exit={0}): {1}".format(
                    result.returncode, error_msg[:500]
                )
            )
    except FileNotFoundError:
        logger.error("Blender executable not found: %s", blender_bin)
        raise BlenderRunnerError("未找到 Blender 可执行文件：{0}".format(blender_bin))
    except subprocess.TimeoutExpired:
        logger.error("Blender execution timed out after %s seconds", timeout)
        raise BlenderRunnerError(
            "Blender 执行超时（{0}秒），可能是场景过于复杂".format(timeout)
        )
    except subprocess.CalledProcessError as e:
        logger.error("Blender process error: %s", str(e))
        raise BlenderRunnerError("Blender 执行失败，exit={0}".format(e.returncode))

    artifacts_path = os.path.join(out_dir, "artifacts.json")
    if not os.path.exists(artifacts_path):
        logger.error("Artifacts file not found: %s", artifacts_path)
        raise BlenderRunnerError("Blender 未生成 artifacts.json，导出可能失败")

    with open(artifacts_path, "r", encoding="utf-8") as f:
        artifacts = json.load(f)

    logger.info("Blender export completed successfully for spec: %s", spec_path)
    return artifacts

