(function () {
  var state = {
    bootstrap: null,
    currentJobId: null,
    pollTimer: null,
    autoTitle: true,
  };

  var stageOrder = [
    "queued",
    "knowledge_ready",
    "blender_exporting",
    "provider_submitted",
    "provider_running",
    "succeeded",
  ];

  var stageLabels = {
    queued: "已创建任务",
    knowledge_ready: "知识检索与 Prompt 编排",
    blender_exporting: "Blender 空间导出",
    provider_submitted: "已提交执行通道",
    provider_running: "视频模型处理中",
    succeeded: "生成完成",
    error: "执行失败",
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function api(path, options) {
    var res = await fetch(path, options || {});
    var contentType = res.headers.get("content-type") || "";
    var payload = null;

    if (contentType.indexOf("application/json") >= 0) {
      payload = await res.json();
    } else {
      payload = await res.text();
    }

    if (!res.ok) {
      var message = "请求失败: " + res.status;
      if (payload && payload.error) {
        message = payload.error;
      } else if (typeof payload === "string" && payload) {
        message = payload;
      }
      throw new Error(message);
    }

    return payload;
  }

  function getVenueById(venueId) {
    var list = (state.bootstrap && state.bootstrap.venue_catalog) || [];
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].id === venueId) {
        return list[i];
      }
    }
    return null;
  }

  function getModelById(modelId) {
    var list = (state.bootstrap && state.bootstrap.model_catalog) || [];
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].id === modelId) {
        return list[i];
      }
    }
    return null;
  }

  function getAssetById(assetId) {
    var list = (state.bootstrap && state.bootstrap.asset_catalog) || [];
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].id === assetId) {
        return list[i];
      }
    }
    return null;
  }

  function getAssetsForVenue(venueId) {
    var allAssets = (state.bootstrap && state.bootstrap.asset_catalog) || [];
    var options = [];
    var i;

    for (i = 0; i < allAssets.length; i += 1) {
      if (allAssets[i].id === "text_only") {
        options.push(allAssets[i]);
      }
    }

    for (i = 0; i < allAssets.length; i += 1) {
      if (allAssets[i].venue_type === venueId) {
        options.push(allAssets[i]);
      }
    }

    return options;
  }

  function getRecommendedAsset(venueId) {
    var assets = getAssetsForVenue(venueId);
    var i;
    for (i = 0; i < assets.length; i += 1) {
      if (assets[i].recommended) {
        return assets[i];
      }
    }
    return assets[0] || null;
  }

  function setStatus(text) {
    if (els.jobStatus) {
      els.jobStatus.textContent = text;
    }
  }

  function renderMetrics(metrics) {
    if (!els.metricsGrid) return;
    els.metricsGrid.innerHTML = "";
    metrics.forEach(function (metric) {
      var card = document.createElement("article");
      card.className = "metric-card";
      card.innerHTML =
        "<strong>" +
        escapeHtml(metric.value) +
        "</strong>" +
        "<span>" +
        escapeHtml(metric.title) +
        "</span>" +
        "<p>" +
        escapeHtml(metric.description) +
        "</p>";
      els.metricsGrid.appendChild(card);
    });
  }

  function renderModels(models) {
    if (!els.modelGrid) return;
    els.modelGrid.innerHTML = "";
    models.forEach(function (model) {
      var routeMode = model.route_mode || "native";
      var badgeClass = routeMode === "demo-route" ? "demo-route" : routeMode;
      var card = document.createElement("article");
      card.className = "model-card";
      card.innerHTML =
        "<header>" +
        "<h3>" +
        escapeHtml(model.display_model) +
        "</h3>" +
        '<span class="route-badge ' +
        escapeHtml(badgeClass) +
        '">' +
        escapeHtml(routeMode) +
        "</span>" +
        "</header>" +
        "<p>" +
        escapeHtml(model.description || "") +
        "</p>" +
        '<div class="model-meta">' +
        (model.recommended ? '<span class="pill recommended">推荐执行</span>' : "") +
        '<span class="pill">provider: ' +
        escapeHtml(model.execution_provider || "") +
        "</span>" +
        "</div>";
      els.modelGrid.appendChild(card);
    });
  }

  function renderAssetCards() {
    if (!els.assetGrid) return;
    var list = (state.bootstrap && state.bootstrap.asset_catalog) || [];
    els.assetGrid.innerHTML = "";
    list.forEach(function (asset) {
      if (asset.showcase === false) {
        return;
      }

      var activeClass = els.assetId && els.assetId.value === asset.id ? " active" : "";
      var card = document.createElement("article");
      card.className = "asset-card" + activeClass;
      card.setAttribute("data-asset-id", asset.id);
      card.innerHTML =
        "<header>" +
        "<h3>" +
        escapeHtml(asset.name) +
        "</h3>" +
        '<span class="asset-badge">' +
        escapeHtml(asset.source_type || "") +
        "</span>" +
        "</header>" +
        "<p>" +
        escapeHtml(asset.description || "") +
        "</p>" +
        '<div class="asset-meta">' +
        '<span class="asset-badge">' +
        escapeHtml(asset.file_format || "") +
        "</span>" +
        '<span class="asset-badge">' +
        escapeHtml((asset.metadata && asset.metadata.capture_pipeline) || "") +
        "</span>" +
        "</div>";
      els.assetGrid.appendChild(card);
    });
  }

  function populateSelect(selectEl, items, formatter, selectedValue) {
    selectEl.innerHTML = "";
    items.forEach(function (item) {
      var option = document.createElement("option");
      option.value = item.id;
      option.textContent = formatter(item);
      if (selectedValue && selectedValue === item.id) {
        option.selected = true;
      }
      selectEl.appendChild(option);
    });
  }

  function populateAssetSelect(venueId, selectedValue) {
    var items = getAssetsForVenue(venueId);
    populateSelect(
      els.assetId,
      items,
      function (asset) {
        return asset.name + " · " + (asset.source_type || asset.asset_kind || "");
      },
      selectedValue
    );
  }

  function applyVenueDefaults() {
    var venue = getVenueById(els.venueType.value);
    if (!venue) {
      return;
    }

    if (state.autoTitle || !els.title.value) {
      els.title.value = venue.hero_title || "";
      state.autoTitle = true;
    }

    if (els.environmentHint) {
      els.environmentHint.value = venue.default_environment || "";
    }
    if (els.lightingHint) {
      els.lightingHint.value = venue.default_lighting || "";
    }

    var defaults = venue.camera_defaults || {};
    if (els.cameraRadius) {
      els.cameraRadius.value = defaults.radius_m || 6.0;
    }
    if (els.cameraHeight) {
      els.cameraHeight.value = defaults.height_m || 1.6;
    }

    populateAssetSelect(venue.id, (getRecommendedAsset(venue.id) || {}).id);
    renderAssetCards();
  }

  function collectPayload() {
    var shotType = els.shotType ? els.shotType.value : "orbit";
    var payload = {
      title: els.title ? els.title.value : "",
      venue_type: els.venueType ? els.venueType.value : "",
      ai_model: els.aiModel ? els.aiModel.value : "",
      asset_id: els.assetId ? els.assetId.value : "",
      shot_type: shotType,
      camera_move_type: shotType,
      duration_s: els.duration ? els.duration.value : 6,
    };

    if (els.environmentHint) payload.environment_hint = els.environmentHint.value;
    if (els.lightingHint) payload.lighting_hint = els.lightingHint.value;

    return payload;
  }

  function renderWarnings(warnings) {
    if (!els.previewWarnings) return;
    if (!warnings || !warnings.length) {
      els.previewWarnings.innerHTML = "";
      return;
    }

    els.previewWarnings.innerHTML = warnings
      .map(function (warning) {
        return '<div class="warning-item">' + escapeHtml(warning) + "</div>";
      })
      .join("");
  }

  function renderPromptPreview(data) {
    if (!els.promptPreview) return;

    if (!data || !data.prompt_bundle) {
      els.promptPreview.innerHTML = '<p class="empty-state">选择场馆后自动生成 Prompt 预览</p>';
      return;
    }

    var bundle = data.prompt_bundle;
    var modules = bundle.modules || {};
    var asset = data.asset_bundle || {};
    var provider = data.execution_provider || bundle.execution_provider || "未指定";
    var displayModel = data.display_model || bundle.display_model || "未指定";

    if (els.executionRoute) {
      els.executionRoute.textContent =
        displayModel + " -> " + provider + " · " + (data.route_mode || bundle.route_mode || "native");
    }

    renderWarnings(data.warnings || []);

    els.promptPreview.innerHTML =
      '<div class="preview-block">' +
      "<h4>六模块 Prompt</h4>" +
      '<div class="module-grid">' +
      '<div class="module-card"><strong>镜头</strong><p>' +
      escapeHtml(modules.camera) +
      "</p></div>" +
      '<div class="module-card"><strong>主体</strong><p>' +
      escapeHtml(modules.subject) +
      "</p></div>" +
      '<div class="module-card"><strong>动态</strong><p>' +
      escapeHtml(modules.dynamics) +
      "</p></div>" +
      '<div class="module-card"><strong>环境</strong><p>' +
      escapeHtml(modules.environment) +
      "</p></div>" +
      '<div class="module-card"><strong>光影</strong><p>' +
      escapeHtml(modules.lighting) +
      "</p></div>" +
      '<div class="module-card"><strong>风格</strong><p>' +
      escapeHtml(modules.style) +
      "</p></div>" +
      "</div>" +
      "</div>" +
      '<div class="preview-block">' +
      "<h4>编排结果</h4>" +
      '<p class="text-block">' +
      escapeHtml(bundle.prompt) +
      "</p>" +
      "</div>" +
      '<div class="preview-block">' +
      "<h4>知识命中</h4>" +
      '<ul class="knowledge-list">' +
      (data.knowledge_hits || [])
        .map(function (item) {
          return (
            "<li><strong>" +
            escapeHtml(item.label || item.id) +
            "</strong><br />" +
            escapeHtml(item.reason || "") +
            "</li>"
          );
        })
        .join("") +
      "</ul>" +
      "</div>";
  }

  function stageIndex(stage) {
    var idx = stageOrder.indexOf(stage);
    return idx >= 0 ? idx : -1;
  }

  function renderStageList(job) {
    if (!els.stageList) return;

    var currentStage = (job && job.stage) || "queued";
    var currentIndex = stageIndex(currentStage);
    var html = stageOrder
      .map(function (stage, index) {
        var className = "";
        if (job && job.status === "error") {
          if (index < currentIndex) {
            className = "done";
          } else if (stage === currentStage) {
            className = "error";
          }
        } else if (currentStage === "succeeded") {
          className = "done";
        } else if (index < currentIndex) {
          className = "done";
        } else if (stage === currentStage) {
          className = "active";
        }

        return (
          '<li class="' +
          className +
          '"><span>' +
          escapeHtml(stageLabels[stage] || stage) +
          "</span><span>" +
          escapeHtml(stage) +
          "</span></li>"
        );
      })
      .join("");

    if (job && job.status === "error" && currentStage === "error") {
      html +=
        '<li class="error"><span>' +
        escapeHtml(stageLabels.error) +
        "</span><span>error</span></li>";
    }

    els.stageList.innerHTML = html;
  }

  function renderJobResult(job) {
    if (!els.jobResult) return;

    if (!job || !job.result) {
      els.jobResult.innerHTML = '<p class="empty-state">任务完成后在此展示视频结果</p>';
      return;
    }

    var result = job.result;
    var provider = result.provider_result || {};
    var artifacts = result.artifacts || {};
    var videoUrl = result.video_url || "";
    var blocks = [];

    blocks.push(
      '<div class="result-block"><h4>Provider 路由</h4><ul class="meta-list">' +
        "<li>展示模型：" +
        escapeHtml(provider.display_model || "未指定") +
        "</li>" +
        "<li>执行通道：" +
        escapeHtml(provider.execution_provider || "未指定") +
        "</li>" +
        "<li>状态：" +
        escapeHtml(provider.status || "not_submitted") +
        "</li>" +
        "</ul></div>"
    );

    blocks.push(
      '<div class="result-block"><h4>Blender / 资产产物</h4><ul class="meta-list">' +
        "<li>导出状态：" +
        escapeHtml(artifacts.status || "skipped") +
        "</li>" +
        "<li>说明：" +
        escapeHtml(artifacts.error || artifacts.reason || artifacts.scene_glb || "无") +
        "</li>" +
        "</ul></div>"
    );

    if (result.warnings && result.warnings.length) {
      blocks.push(
        '<div class="result-block"><h4>降级 / 提示</h4><div class="warning-stack">' +
          result.warnings
            .map(function (warning) {
              return '<div class="warning-item">' + escapeHtml(warning) + "</div>";
            })
            .join("") +
          "</div></div>"
      );
    }

    if (videoUrl) {
      blocks.push(
        '<div class="result-block"><h4>视频结果</h4>' +
          '<video class="result-video" controls preload="metadata">' +
          '<source src="' +
          encodeURI(videoUrl) +
          '" type="video/mp4" />' +
          "</video>" +
          '<p class="text-block">视频直链：<a class="link" target="_blank" rel="noreferrer" href="' +
          encodeURI(videoUrl) +
          '">' +
          escapeHtml(videoUrl) +
          "</a></p></div>"
      );
    } else if (job.status === "error") {
      blocks.push(
        '<div class="result-block"><h4>错误信息</h4><p class="text-block">' +
          escapeHtml(job.error || "未知错误") +
          "</p></div>"
      );
    } else {
      blocks.push('<div class="result-block"><p class="empty-state">任务尚未返回视频结果。</p></div>');
    }

    els.jobResult.innerHTML = blocks.join("");
  }

  function renderJob(job) {
    if (els.jobId) {
      els.jobId.textContent = job && job.id ? job.id : "等待提交";
    }
    renderStageList(job);
    renderJobResult(job);

    if (!job) {
      setStatus("工作台就绪，请配置场景参数后提交任务。");
      return;
    }

    var statusText =
      "状态：" +
      (job.status || "unknown") +
      " · 阶段：" +
      (job.stage || "queued");

    if (job.error) {
      statusText += " · 错误：" + job.error;
    }
    setStatus(statusText);

    if (job.result && job.result.prompt_bundle) {
      renderPromptPreview({
        prompt_bundle: job.result.prompt_bundle,
        knowledge_hits: job.result.knowledge_hits,
        asset_bundle: job.result.asset_bundle,
        warnings: job.result.warnings,
        display_model: job.result.provider_result && job.result.provider_result.display_model,
        execution_provider: job.result.provider_result && job.result.provider_result.execution_provider,
        route_mode: job.result.provider_result && job.result.provider_result.route_mode,
        workflow_mode: job.result.prompt_bundle.workflow_mode,
      });
    }
  }

  function clearPoll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function startPolling(jobId) {
    clearPoll();
    state.currentJobId = jobId;

    state.pollTimer = setInterval(async function () {
      try {
        var job = await api("/api/jobs/" + encodeURIComponent(jobId));
        renderJob(job);
        if (job.status === "succeeded" || job.status === "error") {
          clearPoll();
        }
      } catch (err) {
        clearPoll();
        setStatus("轮询失败：" + err.message);
      }
    }, 4000);
  }

  async function previewPrompt(silent) {
    var payload = collectPayload();
    if (!silent) {
      setStatus("正在生成 Prompt 预览...");
    }
    var data = await api("/api/prompt/preview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    renderPromptPreview(data);
    if (!silent) {
      setStatus("Prompt 预览已更新。");
    }
    return data;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    clearPoll();

    if (els.submitBtn) els.submitBtn.disabled = true;
    if (els.previewBtn) els.previewBtn.disabled = true;
    setStatus("正在创建任务...");

    try {
      await previewPrompt(true);

      var job = await api("/api/jobs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(collectPayload()),
      });

      renderJob(job);
      startPolling(job.id);
    } catch (err) {
      setStatus("创建任务失败：" + err.message);
    } finally {
      if (els.submitBtn) els.submitBtn.disabled = false;
      if (els.previewBtn) els.previewBtn.disabled = false;
    }
  }

  function bindEvents() {
    if (els.title) {
      els.title.addEventListener("input", function () {
        state.autoTitle = false;
      });
    }

    if (els.venueType) {
      els.venueType.addEventListener("change", function () {
        state.autoTitle = true;
        applyVenueDefaults();
        previewPrompt(true).catch(function () {});
      });
    }

    if (els.aiModel) {
      els.aiModel.addEventListener("change", function () {
        previewPrompt(true).catch(function () {});
      });
    }

    if (els.assetId) {
      els.assetId.addEventListener("change", function () {
        renderAssetCards();
        previewPrompt(true).catch(function () {});
      });
    }

    if (els.shotType) {
      els.shotType.addEventListener("change", function () {
        previewPrompt(true).catch(function () {});
      });
    }

    if (els.previewBtn) {
      els.previewBtn.addEventListener("click", function () {
        previewPrompt(false).catch(function (err) {
          setStatus("Prompt 预览失败：" + err.message);
        });
      });
    }

    if (els.form) {
      els.form.addEventListener("submit", handleSubmit);
    }

    if (els.assetGrid) {
      els.assetGrid.addEventListener("click", function (event) {
        var card = event.target.closest("[data-asset-id]");
        var assetId = card && card.getAttribute("data-asset-id");
        var asset = getAssetById(assetId);
        if (!asset) {
          return;
        }

        if (asset.venue_type && els.venueType) {
          els.venueType.value = asset.venue_type;
          state.autoTitle = true;
          applyVenueDefaults();
        }
        if (els.assetId) {
          populateAssetSelect(els.venueType ? els.venueType.value : "", asset.id);
        }
        renderAssetCards();
        previewPrompt(true).catch(function () {});
      });
    }
  }

  function cacheElements() {
    els.metricsGrid = $("metrics-grid");
    els.modelGrid = $("model-grid");
    els.assetGrid = $("asset-grid");
    els.form = $("job-form");
    els.title = $("title");
    els.venueType = $("venue_type");
    els.aiModel = $("ai_model");
    els.assetId = $("asset_id");
    els.shotType = $("shot_type");
    els.duration = $("duration_s");
    els.environmentHint = $("environment_hint");
    els.lightingHint = $("lighting_hint");
    els.previewBtn = $("preview-btn");
    els.submitBtn = $("submit-btn");
    els.jobId = $("job-id");
    els.jobStatus = $("job-status");
    els.stageList = $("stage-list");
    els.executionRoute = $("execution-route");
    els.previewWarnings = $("preview-warnings");
    els.promptPreview = $("prompt-preview");
    els.jobResult = $("job-result");
  }

  async function bootstrap() {
    cacheElements();
    bindEvents();

    setStatus("正在加载项目知识库...");
    if (els.promptPreview) {
      els.promptPreview.innerHTML = '<p class="empty-state">加载中...</p>';
    }
    if (els.jobResult) {
      els.jobResult.innerHTML = '<p class="empty-state">任务完成后在此展示视频结果</p>';
    }

    try {
      state.bootstrap = await api("/api/bootstrap");
      renderMetrics(state.bootstrap.project_metrics || []);
      renderModels(state.bootstrap.model_catalog || []);
      renderAssetCards();

      if (els.venueType) {
        populateSelect(
          els.venueType,
          state.bootstrap.venue_catalog || [],
          function (venue) {
            return venue.name + " · " + (venue.hero_title || "");
          },
          ((state.bootstrap.venue_catalog || [])[0] || {}).id
        );
      }

      if (els.aiModel) {
        populateSelect(
          els.aiModel,
          state.bootstrap.model_catalog || [],
          function (model) {
            return model.display_model + " · " + (model.route_mode || "native");
          },
          ((state.bootstrap.model_catalog || [])[0] || {}).id
        );
      }

      if (els.shotType) {
        populateSelect(
          els.shotType,
          state.bootstrap.shot_catalog || [],
          function (shot) {
            return shot.label;
          },
          ((state.bootstrap.shot_catalog || [])[0] || {}).id
        );
      }

      applyVenueDefaults();
      renderJob(null);
      await previewPrompt(true);
      setStatus("工作台就绪，请配置场景参数后提交任务。");
    } catch (err) {
      setStatus("初始化失败：" + err.message);
      if (els.promptPreview) {
        els.promptPreview.innerHTML = '<p class="empty-state">初始化失败，无法加载 Prompt 预览。</p>';
      }
    }
  }

  bootstrap();
})();