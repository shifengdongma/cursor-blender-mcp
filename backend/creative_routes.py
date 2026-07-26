# -*- coding: utf-8 -*-
"""
Creative Production API routes for AIGV Studio.
"""
from __future__ import absolute_import

from flask import request

from .creative_project_service import get_creative_project_service
from .http_utils import parse_json_body, parse_pagination, require_fields
from .models import CreativeProject, GenerationTask, ExportPackage, TimelineTrack, TimelineClip
from .storyboard_service import get_storyboard_service
from .task_service import get_task_service


def register_creative_routes(app, cfg, json_success, json_error):
    """Register all creative production API routes."""

    project_service = get_creative_project_service()
    storyboard_service = get_storyboard_service()
    task_service = get_task_service()

    # ── Project CRUD ──

    @app.route("/api/creative/projects", methods=["GET"])
    def list_creative_projects():
        tenant_id = request.args.get("tenant_id")
        pagination = parse_pagination(request)
        result = project_service.list_projects(
            tenant_id=tenant_id,
            limit=pagination.limit,
            offset=pagination.offset,
        )
        return json_success(result)

    @app.route("/api/creative/projects", methods=["POST"])
    def create_creative_project():
        data = parse_json_body(request)
        require_fields(data, ["name"])

        project = project_service.create_project(
            name=data.get("name"),
            description=data.get("description"),
            genre=data.get("genre"),
            concept=data.get("concept"),
            requirements=data.get("requirements"),
            creative_brief=data.get("creative_brief"),
            settings=data.get("settings"),
            tenant_id=data.get("tenant_id"),
            project_id=data.get("project_id"),
            user_id=data.get("user_id"),
            status=CreativeProject.STATUS_DRAFT,
        )
        return json_success(project.to_dict(), message="项目已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>", methods=["GET"])
    def get_creative_project(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)
        return json_success(project.to_dict())

    @app.route("/api/creative/projects/<project_id>", methods=["PUT"])
    def update_creative_project(project_id):
        data = parse_json_body(request)
        project = project_service.update_project(project_id, **data)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)
        return json_success(project.to_dict(), message="项目已更新")

    @app.route("/api/creative/projects/<project_id>", methods=["DELETE"])
    def delete_creative_project(project_id):
        success = project_service.delete_project(project_id)
        if not success:
            return json_error("project_not_found", "项目不存在", status_code=404)
        return json_success({"deleted": True}, message="项目已删除")

    # ── Storyboard Analysis ──

    @app.route("/api/creative/projects/<project_id>/analyze", methods=["POST"])
    def analyze_creative_project(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        if not cfg.has_valid_llm_key():
            return json_error("provider_not_configured", "LLM 服务未配置", status_code=400)

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_STORYBOARD,
            params={"project_id": project_id},
        )

        return json_success(task.to_dict(), message="分析任务已创建", status_code=201)

    # ── Storyboard Shots CRUD ──

    @app.route("/api/creative/projects/<project_id>/shots", methods=["GET"])
    def list_storyboard_shots(project_id):
        shots = storyboard_service.list_shots(project_id)
        return json_success([s.to_dict() for s in shots])

    @app.route("/api/creative/projects/<project_id>/shots", methods=["POST"])
    def create_storyboard_shot(project_id):
        data = parse_json_body(request)
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        shot = storyboard_service.create_shot(project_id, **data)
        return json_success(shot.to_dict(), message="分镜已添加", status_code=201)

    @app.route("/api/creative/shots/<shot_id>", methods=["PUT"])
    def update_storyboard_shot(shot_id):
        data = parse_json_body(request)
        shot = storyboard_service.update_shot(shot_id, **data)
        if not shot:
            return json_error("shot_not_found", "分镜不存在", status_code=404)
        return json_success(shot.to_dict(), message="分镜已更新")

    @app.route("/api/creative/shots/<shot_id>", methods=["DELETE"])
    def delete_storyboard_shot(shot_id):
        success = storyboard_service.delete_shot(shot_id)
        if not success:
            return json_error("shot_not_found", "分镜不存在", status_code=404)
        return json_success({"deleted": True}, message="分镜已删除")

    @app.route("/api/creative/shots/reorder", methods=["POST"])
    def reorder_storyboard_shots():
        data = parse_json_body(request)
        require_fields(data, ["project_id", "ordered_ids"])

        storyboard_service.reorder_shots(data["project_id"], data["ordered_ids"])
        return json_success({"reordered": True}, message="顺序已更新")

    # ── Generation Tasks ──

    @app.route("/api/creative/shots/<shot_id>/images", methods=["POST"])
    def generate_shot_images(shot_id):
        shot = storyboard_service.get_shot(shot_id)
        if not shot:
            return json_error("shot_not_found", "分镜不存在", status_code=404)

        if not cfg.has_comfyui_configured():
            return json_error("provider_not_configured", "ComfyUI 图片生成服务未配置", status_code=400)

        data = parse_json_body(request)
        task = task_service.create_task(
            creative_project_id=shot.creative_project_id,
            task_type=GenerationTask.TYPE_IMAGE,
            target_shot_id=shot_id,
            params={
                "width": data.get("width", 1024),
                "height": data.get("height", 576),
                "seed": data.get("seed", -1),
            },
        )

        return json_success(task.to_dict(), message="图片生成任务已创建", status_code=201)

    @app.route("/api/creative/shots/<shot_id>/videos", methods=["POST"])
    def generate_shot_video(shot_id):
        shot = storyboard_service.get_shot(shot_id)
        if not shot:
            return json_error("shot_not_found", "分镜不存在", status_code=404)

        if not cfg.has_valid_api_key():
            return json_error("provider_not_configured", "视频生成服务未配置", status_code=400)

        data = parse_json_body(request)
        task = task_service.create_task(
            creative_project_id=shot.creative_project_id,
            task_type=GenerationTask.TYPE_VIDEO,
            target_shot_id=shot_id,
            params={
                "execution_provider": data.get("execution_provider", "seedance"),
                "prompt": data.get("prompt"),
            },
        )

        return json_success(task.to_dict(), message="视频生成任务已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>/tts", methods=["POST"])
    def generate_project_tts(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        if not cfg.has_piper_configured():
            return json_error("provider_not_configured", "TTS 语音合成服务未配置", status_code=400)

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_TTS,
        )

        return json_success(task.to_dict(), message="TTS 生成任务已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>/compose", methods=["POST"])
    def compose_project_video(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        if not cfg.has_ffmpeg_configured():
            return json_error("provider_not_configured", "FFmpeg 视频合成服务未配置", status_code=400)

        data = parse_json_body(request)
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_COMPOSE,
            params={
                "width": data.get("width", 1920),
                "height": data.get("height", 1080),
                "fps": data.get("fps", 24),
            },
        )

        return json_success(task.to_dict(), message="视频合成任务已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>/refine", methods=["POST"])
    def refine_project_video(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        if not cfg.has_ffmpeg_configured():
            return json_error("provider_not_configured", "FFmpeg 视频精修服务未配置", status_code=400)

        data = parse_json_body(request)
        require_fields(data, ["input_path"])

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_REFINE,
            params=data,
        )

        return json_success(task.to_dict(), message="视频精修任务已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>/exports", methods=["POST"])
    def export_project(project_id):
        project = project_service.get_project(project_id)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_EXPORT,
        )

        return json_success(task.to_dict(), message="导出任务已创建", status_code=201)

    # ── Task Management ──

    @app.route("/api/creative/tasks/<task_id>", methods=["GET"])
    def get_creative_task(task_id):
        task = task_service.get_task(task_id)
        if not task:
            return json_error("task_not_found", "任务不存在", status_code=404)
        return json_success(task.to_dict())

    @app.route("/api/creative/tasks/<task_id>/cancel", methods=["POST"])
    def cancel_creative_task(task_id):
        success = task_service.cancel_task(task_id)
        if not success:
            return json_error("cancel_failed", "取消失败，任务不存在或已完成", status_code=400)
        return json_success({"cancelled": True}, message="任务已取消")

    # ── Artifacts ──

    @app.route("/api/creative/projects/<project_id>/artifacts", methods=["GET"])
    def list_project_artifacts(project_id):
        artifacts = task_service.list_artifacts(creative_project_id=project_id)
        return json_success([a.to_dict() for a in artifacts])

    # ── Timeline ──

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["GET"])
    def get_project_timeline(project_id):
        from .database import get_database
        db = get_database()

        tracks = db.fetch_all(
            "SELECT * FROM timeline_tracks WHERE creative_project_id = ? ORDER BY sequence_no ASC",
            (project_id,),
        )

        result = []
        for track_row in tracks:
            track = TimelineTrack.from_row(track_row)
            clips = db.fetch_all(
                "SELECT * FROM timeline_clips WHERE track_id = ? ORDER BY start_time ASC",
                (track.id,),
            )
            result.append({
                "track": track.to_dict(),
                "clips": [TimelineClip.from_row(c).to_dict() for c in clips],
            })

        return json_success(result)

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["PUT"])
    def save_project_timeline(project_id):
        from .database import get_database
        db = get_database()
        data = parse_json_body(request)
        tracks_data = data.get("tracks") or []

        # Delete existing tracks/clips for this project
        db.delete("timeline_clips", "creative_project_id = ?", (project_id,))
        db.delete("timeline_tracks", "creative_project_id = ?", (project_id,))

        for track_data in tracks_data:
            track = TimelineTrack(
                creative_project_id=project_id,
                name=track_data.get("name", "Track"),
                track_type=track_data.get("track_type", "video"),
                sequence_no=track_data.get("sequence_no", 0),
                settings=track_data.get("settings"),
            )
            db.insert("timeline_tracks", track.to_insert_params())

            clips_data = track_data.get("clips") or []
            for clip_data in clips_data:
                clip = TimelineClip(
                    track_id=track.id,
                    creative_project_id=project_id,
                    shot_id=clip_data.get("shot_id"),
                    asset_id=clip_data.get("asset_id"),
                    name=clip_data.get("name", "Clip"),
                    start_time=clip_data.get("start_time", 0),
                    duration_s=clip_data.get("duration_s", 0),
                    trim_in=clip_data.get("trim_in", 0),
                    trim_out=clip_data.get("trim_out"),
                    properties=clip_data.get("properties"),
                )
                db.insert("timeline_clips", clip.to_insert_params())

        return json_success({"saved": True}, message="时间线已保存")
