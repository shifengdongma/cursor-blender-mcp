from __future__ import absolute_import

import time


class StreamService(object):
    def preview_session(self, payload):
        return self.create_session('preview-job', payload, None)

    def create_session(self, job_id, payload, engine_session):
        profile = payload.get('stream_profile') or 'balanced'
        protocol = 'WebRTC' if profile == 'low_latency' else 'HLS'
        latency_ms = 35 if profile == 'low_latency' else 120 if profile == 'showcase' else 75
        bitrate = 18.0 if profile == 'showcase' else 12.5 if profile == 'balanced' else 9.8
        fps = 72 if (payload.get('engine_target') == 'steamvr_stream') else 30
        return {
            'job_id': job_id,
            'profile': profile,
            'protocol': protocol,
            'bitrate_mbps': bitrate,
            'latency_ms': latency_ms,
            'fps': fps,
            'preview_url': '/demo/stream/{0}'.format(job_id),
            'encoder': 'NVENC-demo',
            'engine_session_id': (engine_session or {}).get('session_id'),
            'created_at': int(time.time()),
        }


def get_stream_service():
    return StreamService()
