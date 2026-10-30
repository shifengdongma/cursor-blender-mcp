# AIGV Studio 媒体工作流（04–06）设计与实现

本文记录 2026-10-30 之后的真实音视频链路。它补充而不是替代 `AIGV_Studio_系统架构文档.md`。

## 1. 数据流

```text
分镜视频资产（03 步）
   │
   ├─ 04 配音：Piper → 每镜头独立 WAV + 独立 SRT → shot_media_versions
   ├─ 04 音频库：上传音乐/音效 → assets(audio_role=music|sfx) → 时间线片段
   ├─ 04 时间线：POST/GET /timeline → timeline_tracks + timeline_clips
   │
   ├─ 05 精修：FFmpeg 确定性调色 → 新视频资产 + 版本行 → 用户选择 original/refined
   │
   └─ 06 合成：compose 任务保存时间线快照 → MediaService.compose_timeline
          → 视频/配音/音乐/音效/字幕 → 校验后的 MP4
          → creative_projects.final_video_asset_id
          → ZIP 导出（final/videos/audio/images/subtitles/manifest/project）
```

所有媒体任务仍然走 Flask + SQLite + 后台 daemon 线程，没有引入微服务或消息队列。

## 2. 数据库增量

迁移由 `backend/database.py` 自动执行，`scripts/migrate_workflow_v2.py` 带备份与校验。版本 2–5：

- `assets.duration_s/audio_role/media_info`
- `storyboard_shots.subtitle_asset_id/audio_options/audio_duration_s`
- `storyboard_shots.selected_video_asset_id/refined_video_asset_id/video_selection_source`
- `creative_projects.timeline_version/final_video_asset_id/final_compose_task_id/final_timeline_version`
- `timeline_tracks.role`
- `timeline_clips.volume/muted/source_audio_enabled/fade_in/fade_out/subtitle_text`
- `generation_tasks.timeline_version/timeline_snapshot` + 阶段计时字段
- `export_packages.asset_id/timeline_version`
- 新表 `shot_media_versions`（视频/音频/字幕历史版本）

旧的 `srt_path` 若指向 `.wav` 会被清空（文件保留），避免字幕与音频混用。

## 3. TTS

### 3.1 音色注册表

`data/tts_voices.json`（`TTS_VOICES_FILE`）只列出服务端真实安装的音色：

```json
{
  "voices": [{
    "id": "piper:zh_CN-huayan-medium",
    "provider": "piper",
    "label": "华言女声（中）",
    "model_path": "zh_CN-huayan-medium.onnx",
    "config_path": "zh_CN-huayan-medium.onnx.json"
  }]
}
```

`model_path` 必须位于 `TTS_MODEL_DIR` 内。`GET /api/creative/tts/voices` 返回可用性、不可用原因和语速/音量能力，不返回模型路径。未安装的模型不会显示为可直接生成。

### 3.2 生成

`POST /api/creative/shots/<shot_id>/tts`：

```json
{"provider":"piper","voice_id":"piper:zh_CN-huayan-medium",
 "text":"旁白文本","speech_rate":1.0,"volume":1.0,
 "client_request_id":"optional-idempotency-key"}
```

- 语速 0.5–2.0 通过 FFmpeg `atempo` 链实现；音量通过 `volume` 实现。无法后处理时直接报错，不静默忽略。
- 输出路径 `data/assets/audio/generated/<task_id>/shot_<shot_id>.wav`，每次生成新建资产，不覆盖历史。
- 同时生成真实 `subtitles/generated/<task_id>/shot_<shot_id>.srt`，写入 `subtitle_asset_id` 与 `srt_path`。TTS 完成时服务端会同步该分镜在已有时间线中的配音/字幕片段并递增版本。
- 历史通过 `GET /api/creative/shots/<shot_id>/audio` 查询；`POST .../audio/selection` 选择历史版本或设为无配音。
- 项目级 `POST /api/creative/projects/<id>/tts` 保留，支持 `mode=missing|all`、`shot_ids` 与同一组音色参数。

## 4. 时间线

`GET /api/creative/projects/<id>/timeline?ensure=1`：

- 首次进入时按分镜顺序读取 `selected_video_asset_id`、真实 FFprobe 时长，生成视频/配音/音乐/音效/字幕轨。
- 已有时间线绝不覆盖；版本从 0 增到 1。
- 无可用视频时返回空时间线与 warning，不创建伪时间线。

`POST /api/creative/projects/<id>/timeline/sync`：把每个分镜当前选中的视频同步到主视频轨；已有片段刷新素材与真实时长，新分镜追加到末尾，并递增时间线版本。适用于第 03 步新增/重新生成视频后。

`PUT /api/creative/projects/<id>/timeline`：

- 必须带 `timeline_version`（旧调用可省略，但新前端总是携带）；版本不一致返回 409。
- 单事务删除/重建本项目时间线；失败整体回滚。
- 校验轨道/角色、视频轨数量与重叠、时间范围、音量/淡入淡出、字幕文本、素材所有权与类型、素材真实时长、配音乐器与分镜关联。
- `properties.loop=true` 的音乐片段可以超过源文件时长并在合成时循环。
- 静音字幕不会进入 SRT/烧录；静音视频不参与合成，全部视频静音时合成接口返回 `timeline_has_no_video`。
- 视频片段可通过时间线块拖动改变起点（0.5 秒吸附），或使用属性面板精确编辑起点/时长/入点/音量/淡入淡出/字幕文本/原声开关。

## 5. 合成

`POST /api/creative/projects/<id>/compose` 在创建任务时固定：

- `timeline_snapshot`（完整时间线）
- `timeline_version`
- 导出参数：720p/1080p、24/25/30 fps、CRF、音频码率、字幕模式、原声开关、音乐 ducking、响度归一。

`MediaService.compose_timeline()`：

- 视频：按时间线顺序裁剪、统一缩放/补边/像素格式/帧率，空隙用黑场补齐，再 concat。
- 音频：
  - 原视频声音（按 clip `source_audio_enabled` 与全局开关）
  - 配音（`atrim + volume + adelay`）
  - 音乐（支持 `-stream_loop -1`、裁切、淡入淡出）
  - 音效（按时间点插入）
  - `amix normalize=0` + `alimiter`，可选 `loudnorm`；可选 `sidechaincompress` ducking。
  - 没有任何音频分支时生成等长静音轨，保证输出容器包含音频轨。
- 字幕：`none` / `mov_text` / `burn`（ASS 风格烧录，使用 `SUBTITLE_FONT_NAME` 中文字体）。
- 输出先写 `.part.mp4`，成功后原子替换；FFprobe 校验流、分辨率、帧率、时长，再用 `ffmpeg -xerror -f null -` 完整解码。
- 产物保存为视频资产 + 字幕资产 + TaskArtifact + `export_packages(format=mp4)`，并把 `creative_projects.final_video_asset_id` 指向该资产。

`GET /api/creative/projects/<id>/final-video` 返回受保护的成片信息；`up_to_date` 比较成片时间线版本与当前版本。

## 6. 精修与版本

`POST /api/creative/projects/<id>/refine` 必须带 `shot_id`，输入资产必须属于该分镜。滤镜白名单：亮度、对比度、饱和度、gamma、曝光（近似映射到 eq）、锐化、模糊、色相、裁切、缩放、帧率、降噪。未知键或空参数直接 400。

精修产生新视频资产，写入 `refined_video_asset_id` 与 `shot_media_versions`，不覆盖原视频。`POST /api/creative/shots/<id>/video-selection` 选择原始/精修版本；若时间线已有该分镜视频片段，同时更新时间线 clip 并递增 `timeline_version`，提示重新合成。

## 7. ZIP 导出

`POST /api/creative/projects/<id>/exports` 使用任务级目录 `data/exports/<task_id>/`，ZIP 结构：

```text
final/final_video.mp4
videos/shot_XXX_video.*
images/shot_XXX_image.*
audio/narration/shot_XXX_narration.*
audio/music/<name>.*
audio/effects/<name>.*
subtitles/subtitles.srt
manifest.json
project.json
```

只打包项目实际存在且当前用户可读的文件；未知/缺失资产跳过并记录在 manifest。下载仍走 `GET /api/creative/tasks/<task_id>/export/download`，路径限定在 `data/exports`。

## 8. 安全边界

- 所有接口经 `require_project` / `require_shot` / `require_asset`，媒体资产校验所有权与类型。
- 不接受服务器路径或任意外部 URL 作为 FFmpeg 输入；只接受 asset_id，由 AssetService 解析受控路径。公开的分镜 PUT 只允许编辑文案/镜头字段和经过类型/权限校验的图片指针；`srt_path`、视频/音频指针、版本选择只能由受校验的专用接口或 worker 写入。
- FFmpeg 使用参数数组，不经过 shell；字幕路径经过 filter 转义。
- 上传音频必须 FFprobe 验证真实音频流；大小受限。
- 时间线保存使用 `BEGIN IMMEDIATE` 事务与版本冲突检测。
- 任务级输出目录避免同项目并发导出/合成互相覆盖。

## 9. 明确未实现

- 多视频轨叠加、转场、关键帧动画。
- 逐字语音强制对齐；当前字幕时间来自实际音频时长或分镜估算。
- AI 超分/视频扩散精修；UI 标注“未接入”，不返回模拟成功。
- 4K 原生、VR/360、多声道。
- 云端 TTS：接口已抽象，本期未启用；没有密钥时不会显示为可用音色。
