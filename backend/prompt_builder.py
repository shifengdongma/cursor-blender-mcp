def build_prompt(scene_spec):
    """
    按文档“黄金六格公式”生成可投喂视频模型的 Prompt。
    这里保持 PoC 级别：重点强调镜头语言、空间、光影、风格锚点。
    """
    cam_type = (((scene_spec or {}).get("camera_move") or {}).get("type") or "orbit").strip()
    camera = {
        "orbit": "Majestic 360-degree orbit shot",
        "dolly_in": "Slow dolly-in shot",
        "crane_up": "Majestic crane shot rising slowly",
        "tracking": "Eye-level tracking shot",
    }.get(cam_type, "Cinematic camera move")

    environment_hint = (scene_spec or {}).get("environment_hint") or "a spacious cultural venue interior"
    lighting_hint = (scene_spec or {}).get("lighting_hint") or "atmospheric volumetric lighting, high contrast chiaroscuro"
    style_anchor = (scene_spec or {}).get("style_anchor") or "High-fidelity architectural visualization, cinematic still, 8k, Unreal Engine 5 style"

    subject = "minimal low-poly blockout scene used as spatial and camera constraint"
    action = "subtle micro-dynamics, dust motes dancing in light beams, curtains subtly swaying"

    prompt = "{camera}, {subject}, {action}, {env}, {light}, {style}.".format(
        camera=camera,
        subject=subject,
        action=action,
        env=environment_hint,
        light=lighting_hint,
        style=style_anchor,
    )

    negative_prompt = (
        "blurry, distorted, warped architecture, broken perspective, low resolution, watermark, text, "
        "shaky camera, flicker, overexposed, underexposed, bad geometry"
    )

    return {"prompt": prompt, "negative_prompt": negative_prompt}

