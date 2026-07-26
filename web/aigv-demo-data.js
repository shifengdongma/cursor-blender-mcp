/**
 * AIGV Studio - Shared Demo Data
 * IIFE pattern, attached as window.AIGV_DEMO_DATA
 */
(function() {
  'use strict';

  var creativeProjects = [
    {
      id: "proj-chu-culture",
      name: "楚文化数字展演宣传片",
      type: "creative_promo",
      venue: "ancient_museum",
      theme: "楚文化",
      elements: "编钟、漆器、青铜器、丝织品",
      audience: "文旅游客、博物馆观众",
      channels: "博物馆大屏、线上展厅、社交媒体",
      duration: 60,
      aspect: "16:9",
      style: "cinematic-realistic",
      mood: "庄重神秘",
      description: "以编钟演奏为主线，通过数字技术重现楚文化的辉煌，展示漆器、青铜器等文物的制作工艺与文化内涵",
      restrictions: "需尊重文物原貌，避免过度娱乐化",
      shots: [
        {
          shotId: "shot-chu-001", projectId: "proj-chu-culture", number: 1, title: "编钟全景",
          duration: 8, shotType: "wide-shot", cameraMove: "dolly-in",
          sceneDesc: "博物馆大厅中央，编钟阵列在灯光下熠熠生辉",
          subjectDesc: "青铜编钟，表面铜绿纹理清晰可见",
          actionDesc: "镜头缓缓推进，编钟渐渐点亮",
          lightingDesc: "暖金色顶光，编钟表面有微弱的金属反光",
          narration: "楚文化，源远流长...",
          keyframePrompt: "musical bronze bells array in museum, warm golden light, cinematic wide shot",
          negativePrompt: "blur, distortion, cartoon",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-chu-002", projectId: "proj-chu-culture", number: 2, title: "漆器细节",
          duration: 6, shotType: "macro", cameraMove: "pan-right",
          sceneDesc: "展柜中的漆器，红色底漆上描绘着精美纹样",
          subjectDesc: "战国漆器，红黑配色，云纹与水波纹",
          actionDesc: "镜头沿漆器表面横向移动",
          lightingDesc: "柔和的展柜照明，局部点光源突出纹饰",
          narration: "漆器工艺，巧夺天工",
          keyframePrompt: "ancient Chinese lacquerware, red and black, intricate cloud patterns, macro detail shot",
          negativePrompt: "blur, modern objects",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-chu-003", projectId: "proj-chu-culture", number: 3, title: "青铜器展示",
          duration: 8, shotType: "medium-shot", cameraMove: "orbit",
          sceneDesc: "青铜鼎在旋转台上展示，四周是博物馆的暗色背景",
          subjectDesc: "商周青铜鼎，饕餮纹，斑驳铜绿",
          actionDesc: "摄影机环绕青铜鼎旋转",
          lightingDesc: "戏剧化顶光，在青铜表面形成高光与阴影对比",
          narration: "青铜重器，国之瑰宝",
          keyframePrompt: "ancient bronze tripod vessel, taotie pattern, dramatic top lighting, orbiting camera",
          negativePrompt: "modern elements, people",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-chu-004", projectId: "proj-chu-culture", number: 4, title: "丝织品复原",
          duration: 7, shotType: "close-up", cameraMove: "static",
          sceneDesc: "复原的楚地丝织品在柔和光线下展示",
          subjectDesc: "丝绸织物，凤鸟纹样，金线刺绣",
          actionDesc: "微风轻拂织物表面，金色流苏轻轻摇曳",
          lightingDesc: "自然光模拟，暖色调",
          narration: "丝路之源，锦绣华章",
          keyframePrompt: "ancient Chinese silk fabric, phoenix pattern, golden embroidery, gentle breeze, soft lighting",
          negativePrompt: "synthetic fabric, harsh shadows",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-chu-005", projectId: "proj-chu-culture", number: 5, title: "整体展陈",
          duration: 10, shotType: "aerial", cameraMove: "crane-down",
          sceneDesc: "从展厅天顶俯视整个楚文化展陈空间",
          subjectDesc: "博物馆展厅，文物陈列布局错落有致",
          actionDesc: "镜头从高处缓缓下降，展现展厅全貌",
          lightingDesc: "环境光与展柜光线的层次感",
          narration: "走进楚文化的世界",
          keyframePrompt: "aerial view of museum exhibition hall, Chu culture artifacts, gradual crane down movement",
          negativePrompt: "people, modern furniture",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-chu-006", projectId: "proj-chu-culture", number: 6, title: "尾篇定格",
          duration: 5, shotType: "wide-shot", cameraMove: "static",
          sceneDesc: "所有展品在柔和的灯光下定格",
          subjectDesc: "编钟、漆器、青铜器、丝织品同框",
          actionDesc: "画面渐暗，标题浮现",
          lightingDesc: "渐暗的暖光，聚光最终停留在中央编钟上",
          narration: "楚韵千年，数字传承",
          keyframePrompt: "museum artifacts display, fading warm light, elegant title card reveal",
          negativePrompt: "abrupt transitions, glitch",
          status: "draft", isDemo: true
        }
      ],
      isDemo: true
    },
    {
      id: "proj-bronze-restoration",
      name: "青铜器数字复原短片",
      type: "restoration_demo",
      venue: "ancient_museum",
      theme: "青铜器修复",
      elements: "商周青铜器、修复工具、科技检测设备",
      audience: "文博专家、文物保护从业者",
      channels: "学术会议、线上培训、博物馆教育",
      duration: 45,
      aspect: "16:9",
      style: "documentary-tech",
      mood: "严谨专业",
      description: "展示青铜器数字化复原全过程，从3D扫描、结构分析到虚拟修复与成品展示",
      restrictions: "需准确反映修复工艺，不可虚构修复步骤",
      shots: [
        {
          shotId: "shot-br-001", projectId: "proj-bronze-restoration", number: 1, title: "扫描准备",
          duration: 6, shotType: "medium-shot", cameraMove: "static",
          sceneDesc: "实验室中，青铜器放置在扫描台上",
          subjectDesc: "西周青铜簋，局部锈蚀，铭文可见",
          actionDesc: "技术人员调整扫描仪位置",
          lightingDesc: "实验室标准照明，无影灯",
          narration: "数字扫描是复原的第一步",
          keyframePrompt: "lab setting, bronze vessel on scanning table, technical lighting, documentary style",
          negativePrompt: "cartoon, fantasy",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-br-002", projectId: "proj-bronze-restoration", number: 2, title: "3D建模",
          duration: 8, shotType: "close-up", cameraMove: "zoom-in",
          sceneDesc: "电脑屏幕上显示青铜器的3D扫描模型",
          subjectDesc: "3D点云数据逐渐形成完整的青铜器模型",
          actionDesc: "屏幕展示数据处理与建模过程",
          lightingDesc: "屏幕光，环境较暗以突出显示内容",
          narration: "高精度建模还原文物原貌",
          keyframePrompt: "3D point cloud reconstruction of bronze artifact, sci-tech visualization, dark environment",
          negativePrompt: "handheld, shaky",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-br-003", projectId: "proj-bronze-restoration", number: 3, title: "结构分析",
          duration: 7, shotType: "wide-shot", cameraMove: "dolly-right",
          sceneDesc: "多屏幕展示青铜器内部结构分析数据",
          subjectDesc: "X光透视、CT扫描截面图",
          actionDesc: "镜头横向移动展示不同分析视角",
          lightingDesc: "蓝白冷色调，科技感",
          narration: "透视结构，分析破损机理",
          keyframePrompt: "multi-screen lab setup, X-ray and CT scans of bronze vessel, blue tech lighting",
          negativePrompt: "warm colors, organic shapes",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-br-004", projectId: "proj-bronze-restoration", number: 4, title: "虚拟修复",
          duration: 10, shotType: "medium-shot", cameraMove: "orbit",
          sceneDesc: "3D软件中进行虚拟拼接与补全",
          subjectDesc: "青铜器碎片在虚拟空间中自动拼合",
          actionDesc: "碎片从散落状态到完整形态的变化动画",
          lightingDesc: "渐变光效，从破碎到完整的过渡",
          narration: "AI辅助虚拟修复，精准还原",
          keyframePrompt: "3D virtual restoration, bronze fragments assembling, glowing effect, clean tech aesthetic",
          negativePrompt: "hand reconstruction, messy",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-br-005", projectId: "proj-bronze-restoration", number: 5, title: "成果对比",
          duration: 6, shotType: "split-screen", cameraMove: "static",
          sceneDesc: "左右分屏展示修复前后对比",
          subjectDesc: "左侧为残缺原件，右侧为数字修复后的完整青铜器",
          actionDesc: "分屏对比静止展示",
          lightingDesc: "均匀照明，确保对比公平性",
          narration: "修复前后，一目了然",
          keyframePrompt: "split screen comparison, before and after bronze restoration, clean presentation",
          negativePrompt: "asymmetry, uneven lighting",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-br-006", projectId: "proj-bronze-restoration", number: 6, title: "成果展示",
          duration: 8, shotType: "wide-shot", cameraMove: "pull-back",
          sceneDesc: "修复完成的青铜器在展厅中以全息投影形式展示",
          subjectDesc: "完整的数字青铜器，金属质感逼真",
          actionDesc: "全息影像缓缓旋转，镜头后拉",
          lightingDesc: "深色背景配合全息光影",
          narration: "青铜器数字复原成果展示",
          keyframePrompt: "holographic projection of restored bronze vessel in dark exhibition space, cinematic",
          negativePrompt: "flat lighting, 2D look",
          status: "draft", isDemo: true
        }
      ],
      isDemo: true
    },
    {
      id: "proj-dunhuang-mural",
      name: "敦煌壁画沉浸式展览",
      type: "immersive_exhibition",
      venue: "modern_gallery",
      theme: "敦煌艺术",
      elements: "壁画、飞天、藻井、琵琶、经变画",
      audience: "艺术爱好者、文化旅游者",
      channels: "沉浸式展厅、VR设备、线上展览",
      duration: 90,
      aspect: "21:9",
      style: "immersive-360",
      mood: "梦幻空灵",
      description: "运用沉浸式投影技术，将敦煌莫高窟壁画以360度环绕方式呈现，让观众身临其境感受千年艺术魅力",
      restrictions: "需保持壁画艺术完整性，不得拼接现代元素",
      shots: [
        {
          shotId: "shot-dh-001", projectId: "proj-dunhuang-mural", number: 1, title: "入口过渡",
          duration: 6, shotType: "fade-in", cameraMove: "static",
          sceneDesc: "从黑暗逐渐显现出沙漠与洞窟的轮廓",
          subjectDesc: "鸣沙山远景，莫高窟外观",
          actionDesc: "画面从全黑渐亮",
          lightingDesc: "黄昏暖光，金色沙丘",
          narration: "踏入敦煌，走进千年石窟",
          keyframePrompt: "Mogao Caves at dusk, golden sand dunes, gradual fade in, cinematic landscape",
          negativePrompt: "modern buildings, people",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-dh-002", projectId: "proj-dunhuang-mural", number: 2, title: "飞天环绕",
          duration: 12, shotType: "immersive", cameraMove: "panoramic",
          sceneDesc: "360度环绕展示壁画中的飞天形象",
          subjectDesc: "敦煌飞天，飘带飞舞，天衣飘扬",
          actionDesc: "飞天从壁画中飞出，环绕观众",
          lightingDesc: "柔和的天光，蓝色天空渐变",
          narration: "飞天舞动，天籁之音",
          keyframePrompt: "Dunhuang flying apsaras, flowing ribbons, 360 immersive, celestial blue sky",
          negativePrompt: "realistic modern clothing, gravity",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-dh-003", projectId: "proj-dunhuang-mural", number: 3, title: "经变画故事",
          duration: 15, shotType: "narrative-sequence", cameraMove: "tracking",
          sceneDesc: "壁画中佛经故事场景活起来",
          subjectDesc: "经变画中的人物与场景动态化",
          actionDesc: "跟随经变画的叙事线移动",
          lightingDesc: "壁画本色还原，局部重点照明",
          narration: "佛经故事，栩栩如生",
          keyframePrompt: "animated Dunhuang mural narratives, buddhist stories, tracking camera, warm palette",
          negativePrompt: "western art style, modern scenes",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-dh-004", projectId: "proj-dunhuang-mural", number: 4, title: "藻井星空",
          duration: 8, shotType: "looking-up", cameraMove: "zoom-out",
          sceneDesc: "仰望洞窟顶部的藻井图案",
          subjectDesc: "莲花藻井，几何图案层层展开",
          actionDesc: "藻井图案无限向上延伸",
          lightingDesc: "顶部光源，从中心向外扩散",
          narration: "仰望藻井，宇宙之美",
          keyframePrompt: "Dunhuang ceiling mandala, infinite geometric pattern, upward zoom, celestial light",
          negativePrompt: "flat ceiling, dark",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-dh-005", projectId: "proj-dunhuang-mural", number: 5, title: "九色鹿传说",
          duration: 10, shotType: "follow-shot", cameraMove: "follow",
          sceneDesc: "九色鹿在山林中奔跑",
          subjectDesc: "白色九色鹿，身披彩色光芒",
          actionDesc: "追随九色鹿穿越山林河流",
          lightingDesc: "森林光影，阳光透过树叶",
          narration: "九色鹿的传说，流传千年",
          keyframePrompt: "nine-color deer from Dunhuang mural, running in forest, magical glowing aura, follow camera",
          negativePrompt: "ordinary deer, urban setting",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-dh-006", projectId: "proj-dunhuang-mural", number: 6, title: "沙漠星辰",
          duration: 10, shotType: "aerial", cameraMove: "pull-back",
          sceneDesc: "从洞窟内逐渐上升到沙漠星空",
          subjectDesc: "莫高窟夜景，银河横跨天际",
          actionDesc: "镜头从洞窟内向后拉升至高空",
          lightingDesc: "月光与星光，洞窟内有微弱烛光",
          narration: "千年敦煌，星空为证",
          keyframePrompt: "Mogao Caves at night, Milky Way above desert, pull-back from cave interior to starry sky",
          negativePrompt: "daylight, city lights",
          status: "draft", isDemo: true
        }
      ],
      isDemo: true
    },
    {
      id: "proj-guqin-art",
      name: "古琴艺术数字传播项目",
      type: "culture_promo",
      venue: "concert_hall",
      theme: "古琴非遗",
      elements: "古琴、琴谱、竹林、水墨",
      audience: "音乐爱好者、非遗传承人",
      channels: "音乐厅大屏、在线平台、短视频",
      duration: 30,
      aspect: "9:16",
      style: "chinese-ink-painting",
      mood: "清雅宁静",
      description: "以古琴演奏为核心，融合中国传统水墨画美学，用数字影像传播古琴艺术的文化内涵与美学价值",
      restrictions: "需尊重古琴传统，弹奏指法要准确",
      shots: [
        {
          shotId: "shot-gq-001", projectId: "proj-guqin-art", number: 1, title: "竹林天籁",
          duration: 6, shotType: "wide-shot", cameraMove: "dolly-in",
          sceneDesc: "竹林深处，一缕阳光穿透",
          subjectDesc: "竹林、石桌、古琴",
          actionDesc: "镜头穿过竹林推进",
          lightingDesc: "清晨阳光穿透竹林，斑驳光影",
          narration: "独坐幽篁里，弹琴复长啸",
          keyframePrompt: "bamboo forest morning light, traditional Chinese ink painting style, serene atmosphere",
          negativePrompt: "urban, neon lights",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-gq-002", projectId: "proj-guqin-art", number: 2, title: "指法细节",
          duration: 5, shotType: "macro", cameraMove: "static",
          sceneDesc: "古琴琴面上手指弹奏的细节",
          subjectDesc: "手指在琴弦上按、拨、滑的指法",
          actionDesc: "聚焦手指技法的特写",
          lightingDesc: "柔和侧光，突出手指与琴弦的关系",
          narration: "勾挑剔抹，音由心生",
          keyframePrompt: "extreme close-up of fingers playing guqin, string detail, soft side lighting, elegant",
          negativePrompt: "blurry, robotic hands",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-gq-003", projectId: "proj-guqin-art", number: 3, title: "水墨晕染",
          duration: 5, shotType: "graphic-overlay", cameraMove: "static",
          sceneDesc: "水墨在宣纸上晕染开，琴音波形叠加",
          subjectDesc: "水墨笔触、音波可视化",
          actionDesc: "水墨扩散与音乐节奏同步",
          lightingDesc: "宣纸白底，墨色层次",
          narration: "水墨与音韵，相得益彰",
          keyframePrompt: "ink wash painting, sound wave visualization, elegant Chinese art style, minimal",
          negativePrompt: "colorful, western style",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-gq-004", projectId: "proj-guqin-art", number: 4, title: "山水意境",
          duration: 6, shotType: "wide-shot", cameraMove: "pan-left",
          sceneDesc: "山水画卷徐徐展开",
          subjectDesc: "传统山水画中的山、水、云、松",
          actionDesc: "镜头跟随画卷横向移动",
          lightingDesc: "自然光模拟，留白美感",
          narration: "高山流水，知音难觅",
          keyframePrompt: "traditional Chinese landscape painting, mountains and water, scroll unfolding, cinematic pan",
          negativePrompt: "3D rendering, realism",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-gq-005", projectId: "proj-guqin-art", number: 5, title: "琴谱传承",
          duration: 5, shotType: "close-up", cameraMove: "zoom-in",
          sceneDesc: "古琴减字谱特写",
          subjectDesc: "泛黄的琴谱，减字谱符号清晰可见",
          actionDesc: "镜头推进至琴谱微距",
          lightingDesc: "暖黄古旧光线",
          narration: "千年琴谱，智慧传承",
          keyframePrompt: "ancient guqin tablature on aged paper, warm vintage lighting, cultural heritage",
          negativePrompt: "digital screen, modern typography",
          status: "draft", isDemo: true
        },
        {
          shotId: "shot-gq-006", projectId: "proj-guqin-art", number: 6, title: "余音袅袅",
          duration: 3, shotType: "wide-shot", cameraMove: "pull-back",
          sceneDesc: "琴声渐远，竹林恢复宁静",
          subjectDesc: "空寂的石桌与古琴",
          actionDesc: "镜头缓缓后拉，琴声渐弱",
          lightingDesc: "黄昏金色余晖",
          narration: "曲终人不见，江上数峰青",
          keyframePrompt: "empty guqin on stone table, bamboo forest at sunset, peaceful, camera slowly pulling back",
          negativePrompt: "crowds, noise",
          status: "draft", isDemo: true
        }
      ],
      isDemo: true
    }
  ];

  // Storyboard shots collected from all projects
  var storyboardShots = [];
  creativeProjects.forEach(function(proj) {
    storyboardShots = storyboardShots.concat(proj.shots);
  });

  var conceptImages = [
    { id: "ci-001", shotId: "shot-chu-001", projectId: "proj-chu-culture", model: "Seedance-1.5", prompt: "musical bronze bells in museum, warm golden light", negativePrompt: "blur, distortion", width: 1920, height: 1080, steps: 50, seed: 12345, url: "", status: "generated", isDemo: true },
    { id: "ci-002", shotId: "shot-chu-002", projectId: "proj-chu-culture", model: "Midjourney-v6", prompt: "ancient Chinese lacquerware, red and black patterns", negativePrompt: "modern objects", width: 1920, height: 1080, steps: 40, seed: 23456, url: "", status: "generated", isDemo: true },
    { id: "ci-003", shotId: "shot-dh-002", projectId: "proj-dunhuang-mural", model: "Seedance-1.5", prompt: "Dunhuang flying apsaras, flowing ribbons, blue sky", negativePrompt: "realistic modern clothing", width: 3840, height: 1080, steps: 60, seed: 34567, url: "", status: "pending", isDemo: true },
    { id: "ci-004", shotId: "shot-gq-001", projectId: "proj-guqin-art", model: "Luma-DreamMachine", prompt: "bamboo forest morning light, ink painting style", negativePrompt: "urban, neon", width: 1080, height: 1920, steps: 45, seed: 45678, url: "", status: "draft", isDemo: true }
  ];

  var videoTasks = [
    { id: "vt-001", shotId: "shot-chu-001", projectId: "proj-chu-culture", duration: 8, cameraType: "dolly-in", motionStrength: 3, stability: 8, resolution: "1080p", fps: 24, model: "Seedance-1.5", status: "completed", progress: 100, isDemo: true },
    { id: "vt-002", shotId: "shot-chu-002", projectId: "proj-chu-culture", duration: 6, cameraType: "pan-right", motionStrength: 2, stability: 9, resolution: "1080p", fps: 24, model: "Seedance-1.5", status: "running", progress: 62, isDemo: true },
    { id: "vt-003", shotId: "shot-dh-002", projectId: "proj-dunhuang-mural", duration: 12, cameraType: "panoramic", motionStrength: 5, stability: 7, resolution: "4K", fps: 30, model: "Luma-DreamMachine", status: "queued", progress: 0, isDemo: true },
    { id: "vt-004", shotId: "shot-gq-004", projectId: "proj-guqin-art", duration: 6, cameraType: "pan-left", motionStrength: 2, stability: 9, resolution: "1080p", fps: 24, model: "Seedance-1.5", status: "error", progress: 0, isDemo: true }
  ];

  var voiceProfiles = [
    { id: "vp-001", name: "庄重男声-楚文化", gender: "male", emotion: "solemn", description: "低沉浑厚的男声，适合历史文化类内容", speed: 1.0, volume: 1.0, isDemo: true },
    { id: "vp-002", name: "空灵女声-敦煌", gender: "female", emotion: "ethereal", description: "空灵清脆的女声，适合艺术沉浸类内容", speed: 1.1, volume: 0.9, isDemo: true },
    { id: "vp-003", name: "专业旁白-青铜器", gender: "male", emotion: "professional", description: "清晰稳重的专业配音", speed: 1.05, volume: 1.0, isDemo: true },
    { id: "vp-004", name: "清雅女声-古琴", gender: "female", emotion: "serene", description: "清雅淡泊的女声，适合传统艺术内容", speed: 0.95, volume: 0.85, isDemo: true }
  ];

  var effectPresets = [
    { id: "ep-001", name: "水墨晕染转场", type: "transition", description: "仿水墨在宣纸上晕染的转场效果", isDemo: true },
    { id: "ep-002", name: "金色粒子特效", type: "particle", description: "金色粒子飘洒效果，适合文物类内容", isDemo: true },
    { id: "ep-003", name: "古卷展开", type: "transition", description: "仿古卷轴展开的片头/片尾效果", isDemo: true },
    { id: "ep-004", name: "光影流转", type: "lighting", description: "光影在展品表面流动的效果", isDemo: true },
    { id: "ep-005", name: "全息投影", type: "post", description: "模拟全息投影视觉效果", isDemo: true }
  ];

  var outputPlatforms = [
    { id: "op-001", name: "博物馆大屏", formats: "MP4 4K/60fps", description: "适配博物馆展厅大型LED屏幕播放", isDemo: true },
    { id: "op-002", name: "线上展厅", formats: "MP4 1080p/30fps", description: "适配网页/小程序在线播放", isDemo: true },
    { id: "op-003", name: "社交媒体", formats: "MP4 1080x1920/30fps", description: "适配抖音、小红书等竖版短视频", isDemo: true },
    { id: "op-004", name: "VR设备", formats: "MP4 360°/立体声", description: "适配VR头显360度播放", isDemo: true }
  ];

  var resourcePools = [
    { id: "pool-local", name: "本地工作站", region: "武汉-光谷", nodeCount: 4, onlineCount: 3, availGpu: 8, avgUtil: 54.2, unitPrice: 0, latency: 2, status: "healthy", isDemo: true },
    { id: "pool-private", name: "私有集群", region: "武汉-数据中心", nodeCount: 8, onlineCount: 8, availGpu: 32, avgUtil: 67.8, unitPrice: 0, latency: 5, status: "healthy", isDemo: true },
    { id: "pool-aliyun", name: "阿里云-杭州", region: "杭州-可用区A", nodeCount: 16, onlineCount: 14, availGpu: 48, avgUtil: 72.3, unitPrice: 12.5, latency: 18, status: "healthy", isDemo: true },
    { id: "pool-tencent", name: "腾讯云-上海", region: "上海-可用区B", nodeCount: 12, onlineCount: 11, availGpu: 36, avgUtil: 61.5, unitPrice: 14.8, latency: 22, status: "healthy", isDemo: true },
    { id: "pool-edge", name: "边缘节点-武汉", region: "武汉-物联网园区", nodeCount: 3, onlineCount: 2, availGpu: 6, avgUtil: 41.0, unitPrice: 0, latency: 8, status: "degraded", isDemo: true }
  ];

  var gpuNodes = [
    { id: "gpu-local-rtx4090-01", name: "local-rtx4090-01", pool: "pool-local", gpuModel: "RTX 4090", gpuCount: 2, totalVram: 48, usedVram: 28.3, utilization: 59, currentTask: "shot-chu-002 渲染中", status: "online", isDemo: true },
    { id: "gpu-private-l40s-02", name: "private-l40s-02", pool: "pool-private", gpuModel: "L40S", gpuCount: 4, totalVram: 192, usedVram: 137.5, utilization: 72, currentTask: "shot-dh-001 排队中", status: "online", isDemo: true },
    { id: "gpu-aliyun-a10-hangzhou-01", name: "aliyun-a10-hangzhou-01", pool: "pool-aliyun", gpuModel: "A10", gpuCount: 8, totalVram: 192, usedVram: 144.2, utilization: 75, currentTask: "批量渲染-青铜器项目", status: "online", isDemo: true },
    { id: "gpu-tencent-a100-shanghai-02", name: "tencent-a100-shanghai-02", pool: "pool-tencent", gpuModel: "A100 80G", gpuCount: 4, totalVram: 320, usedVram: 198.7, utilization: 62, currentTask: "敦煌壁画沉浸式预渲染", status: "online", isDemo: true },
    { id: "gpu-edge-rtx6000-wuhan-01", name: "edge-rtx6000-wuhan-01", pool: "pool-edge", gpuModel: "RTX 6000 Ada", gpuCount: 2, totalVram: 96, usedVram: 52.1, utilization: 54, currentTask: "古琴项目预览渲染", status: "degraded", isDemo: true }
  ];

  var renderSessions = [
    { id: "rs-001", project: "proj-chu-culture", engine: "Blender Cycles", gpuNode: "gpu-local-rtx4090-01", resolution: "1080p", fps: 24, bitrate: "15Mbps", latency: 45, status: "rendering", isDemo: true },
    { id: "rs-002", project: "proj-bronze-restoration", engine: "Blender Eevee", gpuNode: "gpu-private-l40s-02", resolution: "4K", fps: 30, bitrate: "40Mbps", latency: 120, status: "queued", isDemo: true },
    { id: "rs-003", project: "proj-dunhuang-mural", engine: "Unreal Engine", gpuNode: "gpu-tencent-a100-shanghai-02", resolution: "8K", fps: 60, bitrate: "80Mbps", latency: 280, status: "preparing", isDemo: true },
    { id: "rs-004", project: "proj-guqin-art", engine: "Blender Cycles", gpuNode: "gpu-edge-rtx6000-wuhan-01", resolution: "1080p", fps: 24, bitrate: "12Mbps", latency: 65, status: "paused", isDemo: true }
  ];

  var networkLinks = [
    { id: "nl-001", name: "光谷-数据中心主链路", source: "武汉-光谷", target: "武汉-数据中心", latency: 3, jitter: 0.5, packetLoss: 0.01, bandwidth: 10000, health: "excellent", status: "excellent", isDemo: true },
    { id: "nl-002", name: "杭武跨省骨干链路", source: "武汉-数据中心", target: "杭州-可用区A", latency: 18, jitter: 2.1, packetLoss: 0.05, bandwidth: 1000, health: "good", status: "normal", isDemo: true },
    { id: "nl-003", name: "沪武跨省冗余链路", source: "武汉-数据中心", target: "上海-可用区B", latency: 22, jitter: 3.5, packetLoss: 0.08, bandwidth: 800, health: "good", status: "normal", isDemo: true },
    { id: "nl-004", name: "光谷-物联网园边缘链路", source: "武汉-光谷", target: "武汉-物联网园区", latency: 8, jitter: 1.2, packetLoss: 0.12, bandwidth: 500, health: "degraded", status: "unstable", isDemo: true },
    { id: "nl-005", name: "数据中心-云存储内部链路", source: "武汉-数据中心", target: "武汉-存储集群", latency: 1, jitter: 0.1, packetLoss: 0.00, bandwidth: 40000, health: "excellent", status: "excellent", isDemo: true }
  ];

  var sensingNodes = [
    { id: "sn-001", name: "渲染节点-01", gpuModel: "A100 80G", gpuUtil: 72, vramUtil: 68, temp: 67, currentTask: "楚文化影片批量渲染", heartbeat: "2026-07-23 10:20:15", status: "normal", isDemo: true },
    { id: "sn-002", name: "渲染节点-02", gpuModel: "A100 80G", gpuUtil: 88, vramUtil: 82, temp: 74, currentTask: "青铜器建模渲染", heartbeat: "2026-07-23 10:20:12", status: "highload", isDemo: true },
    { id: "sn-003", name: "推理节点-01", gpuModel: "L40S", gpuUtil: 45, vramUtil: 40, temp: 55, currentTask: "AI风格迁移", heartbeat: "2026-07-23 10:20:18", status: "normal", isDemo: true },
    { id: "sn-004", name: "推理节点-02", gpuModel: "L40S", gpuUtil: 12, vramUtil: 18, temp: 42, currentTask: "-", heartbeat: "2026-07-23 10:20:10", status: "standby", isDemo: true },
    { id: "sn-005", name: "边缘节点-01", gpuModel: "RTX 6000 Ada", gpuUtil: 91, vramUtil: 89, temp: 78, currentTask: "展厅实时渲染", heartbeat: "2026-07-23 10:20:08", status: "abnormal", isDemo: true },
    { id: "sn-006", name: "边缘节点-02", gpuModel: "RTX 6000 Ada", gpuUtil: 56, vramUtil: 52, temp: 61, currentTask: "古琴项目预览", heartbeat: "2026-07-23 10:20:14", status: "normal", isDemo: true },
    { id: "sn-007", name: "备份节点-01", gpuModel: "A100 80G", gpuUtil: 0, vramUtil: 2, temp: 35, currentTask: "-", heartbeat: "-", status: "offline", isDemo: true },
    { id: "sn-008", name: "节点切换中", gpuModel: "A100 80G", gpuUtil: 34, vramUtil: 28, temp: 48, currentTask: "故障转移切换中", heartbeat: "2026-07-23 10:20:05", status: "switching", isDemo: true }
  ];

  var storageNodes = [
    { id: "ssd-1", name: "SSD存储阵列-01", capacityTB: 40, usedTB: 25.6, readMBps: 2800, writeMBps: 2100, connections: 24, status: "normal", isDemo: true },
    { id: "ssd-2", name: "SSD存储阵列-02", capacityTB: 40, usedTB: 31.2, readMBps: 2600, writeMBps: 1900, connections: 31, status: "normal", isDemo: true },
    { id: "ssd-3", name: "SSD存储阵列-03", capacityTB: 20, usedTB: 18.4, readMBps: 1800, writeMBps: 1200, connections: 18, status: "warning", isDemo: true },
    { id: "ssd-4", name: "SSD存储阵列-04", capacityTB: 40, usedTB: 8.2, readMBps: 3200, writeMBps: 2800, connections: 12, status: "normal", isDemo: true }
  ];

  var networkSamples = [
    { bandwidth: 9.85, latency: 2.8, packetLoss: 0.01 },
    { bandwidth: 9.92, latency: 2.7, packetLoss: 0.01 },
    { bandwidth: 9.78, latency: 3.1, packetLoss: 0.02 },
    { bandwidth: 9.95, latency: 2.6, packetLoss: 0.01 },
    { bandwidth: 9.88, latency: 2.9, packetLoss: 0.01 },
    { bandwidth: 9.80, latency: 3.3, packetLoss: 0.02 },
    { bandwidth: 9.91, latency: 2.8, packetLoss: 0.01 },
    { bandwidth: 9.86, latency: 3.0, packetLoss: 0.01 },
    { bandwidth: 9.94, latency: 2.5, packetLoss: 0.01 },
    { bandwidth: 9.89, latency: 2.9, packetLoss: 0.02 },
    { bandwidth: 9.79, latency: 3.2, packetLoss: 0.01 },
    { bandwidth: 9.83, latency: 3.4, packetLoss: 0.03 },
    { bandwidth: 9.76, latency: 3.5, packetLoss: 0.02 },
    { bandwidth: 9.90, latency: 2.8, packetLoss: 0.01 },
    { bandwidth: 9.81, latency: 3.1, packetLoss: 0.02 },
    { bandwidth: 9.93, latency: 2.7, packetLoss: 0.01 },
    { bandwidth: 9.87, latency: 2.9, packetLoss: 0.01 },
    { bandwidth: 9.84, latency: 3.0, packetLoss: 0.02 },
    { bandwidth: 9.96, latency: 2.6, packetLoss: 0.01 },
    { bandwidth: 9.82, latency: 3.3, packetLoss: 0.02 }
  ];

  var faultAlerts = [
    { id: "fa-001", level: "critical", type: "gpu", targetId: "sn-005", targetName: "边缘节点-01", reason: "GPU温度持续超过75°C阈值，触发过热保护", time: "2026-07-23 08:45:00", autoRecovery: true, recoveryStatus: "switching", standbyNode: "备份节点-01", confirmed: false, isDemo: true }
  ];

  var switchRecords = [
    { id: "sw-001", time: "2026-07-23 08:45:08", type: "GPU过热切换", source: "边缘节点-01", target: "备份节点-01", reason: "GPU温度超过阈值", duration: 3.2, result: "成功", isDemo: true },
    { id: "sw-002", time: "2026-07-22 16:12:33", type: "链路降级切换", source: "光谷-物联网园边缘链路", target: "光谷-数据中心主链路(旁路)", reason: "丢包率超阈值", duration: 1.8, result: "成功", isDemo: true },
    { id: "sw-003", time: "2026-07-22 09:05:15", type: "存储故障转移", source: "SSD存储阵列-03", target: "SSD存储阵列-04", reason: "磁盘I/O错误", duration: 5.6, result: "成功", isDemo: true },
    { id: "sw-004", time: "2026-07-21 22:30:00", type: "节点维护切换", source: "渲染节点-02", target: "渲染节点-01", reason: "计划内维护", duration: 15.0, result: "成功", isDemo: true },
    { id: "sw-005", time: "2026-07-21 14:18:42", type: "GPU故障迁移", source: "推理节点-01", target: "推理节点-02", reason: "VRAM ECC错误", duration: 4.1, result: "成功", isDemo: true }
  ];

  var alerts = [
    { id: "al-001", level: "warning", type: "resource", node: "edge-rtx6000-wuhan-01", content: "边缘节点GPU利用率持续>50%，建议扩容", time: "2026-07-15 14:30:00", status: "active", isDemo: true },
    { id: "al-002", level: "info", type: "task", node: "gpu-private-l40s-02", content: "青铜器项目批量渲染任务完成", time: "2026-07-15 13:15:00", status: "acknowledged", isDemo: true },
    { id: "al-003", level: "error", type: "network", node: "nl-004", content: "边缘节点链路丢包率超过阈值", time: "2026-07-15 12:45:00", status: "active", isDemo: true },
    { id: "al-004", level: "critical", type: "gpu", node: "gpu-aliyun-a10-hangzhou-01", content: "A10节点显存使用率超过90%", time: "2026-07-15 11:20:00", status: "resolved", isDemo: true }
  ];

  var roles = [
    { id: "role-admin", name: "系统管理员", permissions: { manageUsers: true, manageNodes: true, viewAll: true, manageBilling: true, configureSystem: true }, isDemo: true },
    { id: "role-operator", name: "运维工程师", permissions: { manageUsers: false, manageNodes: true, viewAll: true, manageBilling: false, configureSystem: false }, isDemo: true },
    { id: "role-director", name: "创意总监", permissions: { manageUsers: false, manageNodes: false, viewAll: true, manageBilling: true, configureSystem: false }, isDemo: true },
    { id: "role-artist", name: "数字艺术家", permissions: { manageUsers: false, manageNodes: false, viewAll: false, manageBilling: false, configureSystem: false }, isDemo: true }
  ];

  var billingRecords = [
    { date: "2026-07-15", dailyCost: 186.50, weeklyCost: 1245.80, monthlyCost: 4826.30, gpuCost: 3210.00, renderCost: 980.50, storageCost: 358.80, networkCost: 277.00, isDemo: true },
    { date: "2026-07-14", dailyCost: 215.20, weeklyCost: 1186.40, monthlyCost: 4639.80, gpuCost: 3098.00, renderCost: 1052.30, storageCost: 352.50, networkCost: 237.00, isDemo: true },
    { date: "2026-07-13", dailyCost: 178.90, weeklyCost: 1120.60, monthlyCost: 4424.60, gpuCost: 2950.00, renderCost: 876.20, storageCost: 348.40, networkCost: 250.00, isDemo: true },
    { date: "2026-07-12", dailyCost: 163.40, weeklyCost: 1089.20, monthlyCost: 4245.70, gpuCost: 2840.00, renderCost: 815.30, storageCost: 342.40, networkCost: 248.00, isDemo: true }
  ];

  var opsEvents = [
    { id: "ev-001", alertId: "al-001", action: "发送扩容提醒", timestamp: "2026-07-15 14:35:00", description: "系统自动检测到边缘节点GPU利用率持续偏高，已向运维团队发送扩容建议通知", isDemo: true },
    { id: "ev-002", alertId: "al-002", action: "任务完成通知", timestamp: "2026-07-15 13:20:00", description: "青铜器项目批量渲染所有帧已完成，输出文件已存入素材库", isDemo: true },
    { id: "ev-003", alertId: "al-003", action: "自动切换链路", timestamp: "2026-07-15 12:50:00", description: "边缘节点链路丢包率超过阈值，系统自动切换到备用链路", isDemo: true },
    { id: "ev-004", alertId: "al-004", action: "弹性扩容", timestamp: "2026-07-15 11:25:00", description: "A10节点显存使用率达到90%，触发自动扩容，新增2个GPU实例", isDemo: true },
    { id: "ev-005", alertId: null, action: "例行维护", timestamp: "2026-07-15 02:00:00", description: "系统执行每日例行备份与性能巡检，所有服务正常运行", isDemo: true }
  ];

  var filmKeyframes = [
    { id: "fk-001", index: 1, title: "全景开场", lensDesc: "广角镜头", duration: 8, description: "博物馆大厅全景，编钟阵列在灯光下熠熠生辉", color: "#78bfd2", isDemo: true },
    { id: "fk-002", index: 2, title: "编钟特写", lensDesc: "长焦特写", duration: 6, description: "青铜编钟特写，铜绿纹理清晰可见", color: "#d7a84f", isDemo: true },
    { id: "fk-003", index: 3, title: "漆器细节", lensDesc: "微距镜头", duration: 6, description: "展柜中的漆器，红黑配色精美纹样", color: "#c9876e", isDemo: true },
    { id: "fk-004", index: 4, title: "青铜器旋转", lensDesc: "环绕镜头", duration: 8, description: "青铜鼎在旋转台上360度展示", color: "#94ddf1", isDemo: true },
    { id: "fk-005", index: 5, title: "丝织品", lensDesc: "特写镜头", duration: 7, description: "楚地丝织品复原，金线刺绣凤鸟纹", color: "#e8c97a", isDemo: true },
    { id: "fk-006", index: 6, title: "展厅全貌", lensDesc: "俯拍航拍", duration: 10, description: "从高空俯瞰整个楚文化展陈空间", color: "#5fa8b8", isDemo: true },
    { id: "fk-007", index: 7, title: "编钟演奏", lensDesc: "动态轨道", duration: 12, description: "编钟动画演奏，模拟古乐响起", color: "#f0d060", isDemo: true },
    { id: "fk-008", index: 8, title: "尾篇定格", lensDesc: "静态镜头", duration: 5, description: "所有展品同框，画面渐暗标题浮现", color: "#604020", isDemo: true }
  ];

  var archMaterialPresets = [
    { id: "arch-mat-matte", name: "哑光", roughness: 0.8, metalness: 0.0, color: "#d4c5a9", description: "传统建筑外立面哑光质感", isDemo: true },
    { id: "arch-mat-metal", name: "金属", roughness: 0.2, metalness: 0.9, color: "#b8b8c8", description: "钢结构与金属幕墙", isDemo: true },
    { id: "arch-mat-glass", name: "玻璃", roughness: 0.1, metalness: 0.1, color: "#88ccff", description: "玻璃幕墙透明反射效果", isDemo: true },
    { id: "arch-mat-ceramic", name: "陶瓷", roughness: 0.3, metalness: 0.0, color: "#f5f0e0", description: "陶瓷面板与装饰构件", isDemo: true },
    { id: "arch-mat-wood", name: "木纹", roughness: 0.6, metalness: 0.0, color: "#8b6914", description: "木质结构与装饰面层", isDemo: true },
    { id: "arch-mat-raw", name: "原始", roughness: 1.0, metalness: 0.0, color: "#888888", description: "素混凝土 / 毛坯质感", isDemo: true }
  ];

  var archLightingPresets = [
    { id: "arch-lit-daylight", name: "日光", ambientColor: "#ffffff", ambientIntensity: 0.4, sunColor: "#fffde8", sunIntensity: 1.0, sunPos: [10, 15, 5], bgColor: "#87ceeb", description: "正午自然日光", isDemo: true },
    { id: "arch-lit-studio", name: "影棚", ambientColor: "#ffffff", ambientIntensity: 0.6, sunColor: "#ffffff", sunIntensity: 0.5, sunPos: [0, 10, 0], bgColor: "#404040", description: "影棚均匀布光", isDemo: true },
    { id: "arch-lit-warm", name: "暖画廊", ambientColor: "#ffeedd", ambientIntensity: 0.3, sunColor: "#ffe0a0", sunIntensity: 0.7, sunPos: [3, 12, 2], bgColor: "#f5e6d3", description: "暖色调画廊光线", isDemo: true },
    { id: "arch-lit-cold", name: "冷工业", ambientColor: "#ddeeff", ambientIntensity: 0.3, sunColor: "#ddddff", sunIntensity: 0.6, sunPos: [-5, 8, 3], bgColor: "#8899aa", description: "冷色调工业光线", isDemo: true },
    { id: "arch-lit-night", name: "夜景", ambientColor: "#224466", ambientIntensity: 0.5, sunColor: "#224477", sunIntensity: 0.3, sunPos: [1, 2, 5], bgColor: "#112244", description: "夜景城市灯光", isDemo: true },
    { id: "arch-lit-silhouette", name: "剪影", ambientColor: "#000000", ambientIntensity: 0.1, sunColor: "#ffaa44", sunIntensity: 2.0, sunPos: [-8, 3, -5], bgColor: "#000000", description: "强烈逆光剪影", isDemo: true }
  ];

  var archEffectImages = [
    { id: "arch-img-001", label: "日光渲染效果", description: "日光·哑光材质", presetMaterial: "arch-mat-matte", presetLighting: "arch-lit-daylight", isDemo: true },
    { id: "arch-img-002", label: "夜景渲染效果", description: "夜景·金属材质", presetMaterial: "arch-mat-metal", presetLighting: "arch-lit-night", isDemo: true },
    { id: "arch-img-003", label: "展厅渲染效果", description: "暖光·陶瓷材质", presetMaterial: "arch-mat-ceramic", presetLighting: "arch-lit-warm", isDemo: true }
  ];

  var gameExhibits = [
    { id: "game-exh-001", name: "青铜编钟", color: "#78bfd2", shape: "cylinder", pos: [-8, 0, -6], description: "战国青铜编钟复原件", isDemo: true },
    { id: "game-exh-002", name: "漆器展柜", color: "#c9876e", shape: "box", pos: [-8, 0, 6], description: "楚文化漆器精品", isDemo: true },
    { id: "game-exh-003", name: "青铜鼎", color: "#5fa8b8", shape: "torus", pos: [8, 0, -6], description: "商周青铜鼎 3D数字模型", isDemo: true },
    { id: "game-exh-004", name: "丝织品", color: "#e8c97a", shape: "cone", pos: [8, 0, 6], description: "复原楚地丝织品", isDemo: true },
    { id: "game-exh-005", name: "漆木虎座", color: "#d7a84f", shape: "dodecahedron", pos: [-8, 0, 0], description: "漆木虎座飞鸟雕塑", isDemo: true },
    { id: "game-exh-006", name: "竹简书卷", color: "#8b6914", shape: "icosahedron", pos: [8, 0, 0], description: "楚简文字数字化展示", isDemo: true }
  ];

  window.AIGV_DEMO_DATA = {
    creativeProjects: creativeProjects,
    storyboardShots: storyboardShots,
    conceptImages: conceptImages,
    videoTasks: videoTasks,
    voiceProfiles: voiceProfiles,
    effectPresets: effectPresets,
    outputPlatforms: outputPlatforms,
    resourcePools: resourcePools,
    gpuNodes: gpuNodes,
    renderSessions: renderSessions,
    networkLinks: networkLinks,
    sensingNodes: sensingNodes,
    storageNodes: storageNodes,
    networkSamples: networkSamples,
    faultAlerts: faultAlerts,
    switchRecords: switchRecords,
    alerts: alerts,
    roles: roles,
    billingRecords: billingRecords,
    opsEvents: opsEvents,
    filmKeyframes: filmKeyframes,
    archMaterialPresets: archMaterialPresets,
    archLightingPresets: archLightingPresets,
    archEffectImages: archEffectImages,
    gameExhibits: gameExhibits
  };
})();
