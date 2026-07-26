import time
import requests


class SeedanceError(RuntimeError):
    pass


class SeedanceProvider(object):
    """
    Atlas Cloud / Seedance 文生视频 Provider（PoC）。

    参考：https://www.atlascloud.ai/zh/blog/how-to-access-seedance-2-0-api-free

    - 启动生成：POST {base_url}/model/generateVideo
    - 轮询结果：GET  {base_url}/model/prediction/{prediction_id}
    """

    def __init__(self, api_key, base_url, model_name=None):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        # 默认使用文生视频模型
        self.model_name = (
            model_name
            or "bytedance/seedance-v1.5-pro/text-to-video"
        )

    def _headers(self):
        return {
            "Authorization": "Bearer {k}".format(k=self.api_key),
            "Content-Type": "application/json",
        }

    def create_generation(
        self,
        prompt,
        negative_prompt=None,
        keyframe_urls=None,
        aspect_ratio="16:9",
        duration_s=8,
        resolution="720p",
    ):
        """
        启动一次 Seedance 文生视频任务。

        PoC：仅用 text prompt，不额外传 negative_prompt / keyframes，
        以保证与官方示例兼容。
        """
        if not self.api_key:
            raise SeedanceError("SEEDANCE_API_KEY 未配置")

        payload = {
            "model": self.model_name,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": False,
            "duration": int(duration_s),
            "generate_audio": True,
            "prompt": prompt,
            "resolution": resolution,
            "seed": -1,
        }

        url = self.base_url + "/model/generateVideo"
        r = requests.post(url, headers=self._headers(), json=payload, timeout=120)
        if r.status_code >= 400:
            raise SeedanceError(
                "Seedance create failed: {code} {text}".format(
                    code=r.status_code, text=r.text[:1000]
                )
            )
        data = r.json() or {}
        data_obj = data.get("data") or {}
        pred_id = data_obj.get("id")
        if not pred_id:
            raise SeedanceError("Seedance 返回缺少 data.id 字段: {0}".format(data))
        return data

    def get_generation(self, prediction_id):
        """
        轮询视频生成状态。
        """
        if not self.api_key:
            raise SeedanceError("SEEDANCE_API_KEY 未配置")
        url = self.base_url + "/model/prediction/{pid}".format(pid=prediction_id)
        r = requests.get(url, headers={"Authorization": "Bearer {k}".format(k=self.api_key)}, timeout=60)
        if r.status_code >= 400:
            raise SeedanceError(
                "Seedance poll failed: {code} {text}".format(
                    code=r.status_code, text=r.text[:1000]
                )
            )
        return r.json() or {}

    @staticmethod
    def extract_status(pred_json):
        """
        常见形态：data.status
        """
        data = (pred_json or {}).get("data") or {}
        status = data.get("status")
        if status:
            return status
        return "unknown"

    @staticmethod
    def extract_video_url(pred_json):
        """
        常见形态：data.outputs[0] 为视频 URL。
        """
        data = (pred_json or {}).get("data") or {}
        outputs = data.get("outputs") or []
        if isinstance(outputs, list) and outputs:
            # 第一项通常是视频 URL
            return outputs[0]
        return None

    def wait_until_done(self, prediction_id, timeout_s=900, poll_interval_s=5):
        """
        轮询直到生成完成或失败。
        """
        start = time.time()
        last = None
        while time.time() - start < timeout_s:
            last = self.get_generation(prediction_id)
            status = (self.extract_status(last) or "").lower()
            video_url = self.extract_video_url(last)

            if status in ("completed", "succeeded", "success", "done") and video_url:
                return last

            if status in ("failed", "error", "canceled", "cancelled"):
                return last

            time.sleep(poll_interval_s)

        if last is None:
            raise SeedanceError("Seedance 轮询超时且无有效响应")
        last["_timeout"] = True
        return last

