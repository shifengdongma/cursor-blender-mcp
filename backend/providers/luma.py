import time
import requests


class LumaError(RuntimeError):
    pass


class LumaProvider(object):
    """
    Luma Dream Machine provider（PoC）。
    注意：Luma 的字段/状态名可能随版本变化，因此这里尽量做“宽松解析 + 原始响应保留”。
    """

    def __init__(self, api_key, base_url):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")

    def _headers(self):
        return {
            "Authorization": "Bearer {k}".format(k=self.api_key),
            "Content-Type": "application/json",
        }

    def create_generation(self, prompt, negative_prompt=None, keyframe_urls=None, aspect_ratio="16:9"):
        if not self.api_key:
            raise LumaError("LUMA_API_KEY 未配置")

        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }

        # PoC：可按需扩展 negative_prompt、keyframes
        if keyframe_urls:
            payload["keyframes"] = {
                "frame0": {"type": "image", "url": keyframe_urls[0]},
            }

        url = self.base_url + "/generations"
        r = requests.post(url, json=payload, headers=self._headers(), timeout=60)
        if r.status_code >= 400:
            raise LumaError("Luma create failed: {code} {text}".format(code=r.status_code, text=r.text[:1000]))
        data = r.json()
        gen_id = data.get("id") or data.get("generation_id") or ""
        if not gen_id:
            raise LumaError("Luma 返回缺少 id 字段: {0}".format(data))
        return data

    def get_generation(self, generation_id):
        if not self.api_key:
            raise LumaError("LUMA_API_KEY 未配置")
        url = self.base_url + "/generations/{gid}".format(gid=generation_id)
        r = requests.get(url, headers={"Authorization": "Bearer {k}".format(k=self.api_key)}, timeout=60)
        if r.status_code >= 400:
            raise LumaError("Luma poll failed: {code} {text}".format(code=r.status_code, text=r.text[:1000]))
        return r.json()

    @staticmethod
    def extract_status(gen_json):
        for k in ("state", "status"):
            v = gen_json.get(k)
            if v:
                return v
        return "unknown"

    @staticmethod
    def extract_video_url(gen_json):
        # 常见形态：assets.video 或 output.video_url 等
        assets = gen_json.get("assets") or {}
        if isinstance(assets, dict):
            if assets.get("video"):
                return assets.get("video")
            if assets.get("video_url"):
                return assets.get("video_url")

        output = gen_json.get("output") or {}
        if isinstance(output, dict):
            if output.get("video_url"):
                return output.get("video_url")

        return None

    def wait_until_done(self, generation_id, timeout_s=900, poll_interval_s=5):
        start = time.time()
        last = None
        while time.time() - start < timeout_s:
            last = self.get_generation(generation_id)
            status = self.extract_status(last)
            video_url = self.extract_video_url(last)

            if status.lower() in ("completed", "succeeded", "success", "done") and video_url:
                return last

            if status.lower() in ("failed", "error", "canceled", "cancelled"):
                return last

            time.sleep(poll_interval_s)

        if last is None:
            raise LumaError("Luma 轮询超时且无有效响应")
        last["_timeout"] = True
        return last

