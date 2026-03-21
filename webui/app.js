const state = {
  bootstrap: null,
  source: null,
  preview: null,
  recentImages: [],
  regions: [],
  dragging: false,
  dragStart: null,
  dragDepth: 0,
  batch: {
    jobId: 0,
    nextOffset: 0,
    polling: false,
  },
  ui: {
    sidebarPage: 'file',
    fontPreviewToken: 0,
    fontPreviewFace: null,
    onlineFontItems: [],
    recentDownloadedFonts: [],
    fontHighlightTimer: null,
    pixivLlmModels: [],
    lastSavedSettingsSnapshot: '',
  },
};

const refs = {};
let initialized = false;
let startupFallbackTimer = null;
let batchPollHandle = null;
let settingsSaveHandle = null;
const PIXIV_AUTOSAVE_DELAY = 500;
const DEFAULT_WATERMARK_SAMPLE = 'YourName · 水印预览 2026';

window.addEventListener('pywebviewready', maybeInit);
window.addEventListener('DOMContentLoaded', maybeInit);
window.addEventListener('resize', () => renderRegions());

if (document.readyState === 'complete' || document.readyState === 'interactive') {
  window.setTimeout(maybeInit, 0);
}

function maybeInit() {
  cacheRefs();
  showStartupOverlay(
    '正在连接桌面工作台',
    '第一次启动时会稍慢一点，正在等待前端和 Python 桥接就绪。',
  );

  if (initialized) {
    return;
  }

  if (!window.pywebview || !window.pywebview.api) {
    if (!startupFallbackTimer) {
      startupFallbackTimer = window.setTimeout(() => {
        showStartupOverlay(
          '仍在等待桌面桥接',
          '如果长时间没有反应，可以先关闭当前窗口，然后双击 start_webview.bat 查看可见启动信息。',
        );
      }, 2500);
    }
    return;
  }

  initialized = true;
  if (startupFallbackTimer) {
    clearTimeout(startupFallbackTimer);
    startupFallbackTimer = null;
  }

  init().catch((error) => {
    console.error(error);
    showStartupOverlay('启动失败', String(error && error.message ? error.message : error));
    pushLog(`启动失败: ${error}`);
    updateStatusBadge('状态: 启动失败');
  });
}

async function init() {
  cacheRefs();
  bindEvents();

  const result = await window.pywebview.api.get_bootstrap_data();
  if (!result.ok) {
    pushLog(result.error || '初始化失败');
    updateStatusBadge('状态: 初始化失败');
    showStartupOverlay('启动失败', result.error || '初始化失败');
    return;
  }

  state.bootstrap = result;
  hydrateStaticOptions(result);
  hydrateForm(result.config);
  initSidebarTabs();
  updateRecentImages(result.recentImages || []);
  renderRegionChips();

  if (result.source) {
    updateSource(result.source);
    updatePreview(result.preview || result.source);
  }

  updateStatusBadge(result.message || '准备就绪');
  pushLog('PyWebView 工作台已载入');
  hideStartupOverlay();
}

function cacheRefs() {
  const ids = [
    'startupOverlay',
    'startupTitle',
    'startupMessage',
    'sidebarTabbar',
    'currentFile',
    'recentList',
    'openImageBtn',
    'wmEnabled',
    'wmText',
    'wmFontPreset',
    'wmFontPath',
    'browseFontBtn',
    'wmFontPreview',
    'fontSampleCard',
    'wmFontSample',
    'wmSampleMode',
    'fontApiKey',
    'fontCatalogQuery',
    'loadOnlineFontsBtn',
    'onlineFontList',
    'downloadOnlineFontBtn',
    'fontCatalogStatus',
    'recentFontList',
    'wmPosition',
    'wmFontSize',
    'wmOpacity',
    'wmColor',
    'wmRotMin',
    'wmRotMax',
    'wmRandomOffset',
    'mosaicEnabled',
    'mosaicMode',
    'mosaicPixelSize',
    'mosaicBlurRadius',
    'processOrder',
    'regionList',
    'undoRegionBtn',
    'clearRegionsBtn',
    'upscaleEnabled',
    'upscaleEngine',
    'upscaleModel',
    'upscaleCustomModel',
    'browseModelBtn',
    'upscaleScale',
    'upscaleNoise',
    'startBatchBtn',
    'stopBatchBtn',
    'batchInputDir',
    'browseBatchInputBtn',
    'batchOutputDir',
    'browseBatchOutputBtn',
    'batchStatusText',
    'batchProgressLabel',
    'batchProgressFill',
    'batchCurrentFile',
    'batchSummary',
    'pixivEnabled',
    'pixivUploadMode',
    'pixivBrowser',
    'pixivVisibility',
    'pixivAge',
    'pixivSubmitMode',
    'pixivTagLanguage',
    'pixivSafetyMode',
    'pixivProfileDir',
    'browsePixivProfileBtn',
    'pixivCookie',
    'pixivCsrfToken',
    'pixivLlmEnabled',
    'pixivLlmImageEnabled',
    'pixivLlmBaseUrl',
    'pixivLlmApiKey',
    'pixivRememberLlmApiKey',
    'loadPixivLlmModelsBtn',
    'testPixivLlmBtn',
    'pixivLlmModelPreset',
    'pixivLlmModelCustom',
    'pixivLlmTemperature',
    'pixivLlmTimeout',
    'pixivLlmPromptMetadata',
    'pixivLlmPromptImage',
    'pixivTitleTemplate',
    'pixivTags',
    'pixivCaption',
    'pixivLockTags',
    'pixivUseMetadataTags',
    'pixivIncludeLoraTags',
    'pixivAddOriginalTag',
    'pixivAiGenerated',
    'pixivAddUpscaleTag',
    'pixivAddEngineTag',
    'pixivAddModelTag',
    'pixivAddScaleTag',
    'pixivModeHint',
    'pixivSaveState',
    'resetPreviewBtn',
    'renderPreviewBtn',
    'exportBtn',
    'badgeSourceSize',
    'badgePreviewSize',
    'badgeRegionCount',
    'badgeStatus',
    'sourceMeta',
    'resultMeta',
    'sourceViewport',
    'resultViewport',
    'sourceStage',
    'resultStage',
    'sourceImage',
    'resultImage',
    'selectionLayer',
    'dragSelection',
    'sourceDropOverlay',
    'resultDropOverlay',
    'sourceEmpty',
    'resultEmpty',
    'logList',
    'clearLogBtn',
  ];

  ids.forEach((id) => {
    refs[id] = document.getElementById(id);
  });
}

function bindEvents() {
  refs.openImageBtn.addEventListener('click', onOpenImage);
  refs.browseFontBtn.addEventListener('click', onBrowseFont);
  refs.browseModelBtn.addEventListener('click', onBrowseModel);
  refs.browseBatchInputBtn.addEventListener('click', () => {
    void onBrowseDirectory(refs.batchInputDir, '已选择批量输入目录');
  });
  refs.browseBatchOutputBtn.addEventListener('click', () => {
    void onBrowseDirectory(refs.batchOutputDir, '已选择批量输出目录');
  });
  refs.browsePixivProfileBtn.addEventListener('click', () => {
    void onBrowseDirectory(refs.pixivProfileDir, '已选择 Pixiv 资料目录');
  });
  refs.pixivUploadMode.addEventListener('change', syncPixivFieldState);
  refs.pixivSubmitMode.addEventListener('change', updatePixivModeHint);
  refs.pixivSafetyMode.addEventListener('change', updatePixivModeHint);
  refs.pixivLlmEnabled.addEventListener('change', syncPixivFieldState);
  refs.pixivLlmImageEnabled.addEventListener('change', updatePixivModeHint);
  refs.pixivLlmModelPreset.addEventListener('change', syncPixivLlmModelState);
  refs.loadPixivLlmModelsBtn.addEventListener('click', onLoadPixivLlmModels);
  refs.testPixivLlmBtn.addEventListener('click', onTestPixivLlm);
  refs.startBatchBtn.addEventListener('click', onStartBatch);
  refs.stopBatchBtn.addEventListener('click', onStopBatch);
  refs.renderPreviewBtn.addEventListener('click', onRenderPreview);
  refs.exportBtn.addEventListener('click', onExport);
  refs.resetPreviewBtn.addEventListener('click', onResetPreview);
  refs.undoRegionBtn.addEventListener('click', undoLastRegion);
  refs.clearRegionsBtn.addEventListener('click', clearRegions);
  refs.clearLogBtn.addEventListener('click', () => {
    refs.logList.innerHTML = '';
  });
  document.querySelectorAll('.sidebar-tab').forEach((button) => {
    button.addEventListener('click', () => {
      setSidebarPage(button.dataset.page || 'file');
    });
  });
  refs.wmFontPreset.addEventListener('change', onWatermarkFontPresetChange);
  refs.wmFontPath.addEventListener('input', updateWatermarkFontPreview);
  refs.wmFontPath.addEventListener('change', syncWatermarkFontState);
  refs.wmText.addEventListener('input', updateWatermarkSampleText);
  refs.wmSampleMode.addEventListener('change', updateWatermarkSampleText);
  refs.loadOnlineFontsBtn.addEventListener('click', onLoadOnlineFonts);
  bindSettingsAutosave();
  refs.downloadOnlineFontBtn.addEventListener('click', onDownloadOnlineFont);
  document.querySelectorAll('[data-font-query]').forEach((button) => {
    button.addEventListener('click', () => {
      refs.fontCatalogQuery.value = button.dataset.fontQuery || '';
      void onLoadOnlineFonts();
    });
  });
  refs.upscaleEngine.addEventListener('change', onEngineChange);
  refs.mosaicMode.addEventListener('change', updateMosaicFieldState);
  refs.pixivEnabled.addEventListener('change', syncPixivFieldState);
  refs.sourceStage.addEventListener('mousedown', onSourceMouseDown);
  window.addEventListener('mousemove', onSourceMouseMove);
  window.addEventListener('mouseup', onSourceMouseUp);
  window.addEventListener('keydown', onWorkspaceKeyDown);
  window.addEventListener('beforeunload', stopBatchPolling);

  [refs.sourceViewport, refs.resultViewport].forEach((element) => {
    element.addEventListener('dragenter', onWorkspaceDragEnter);
    element.addEventListener('dragover', onWorkspaceDragOver);
    element.addEventListener('dragleave', onWorkspaceDragLeave);
    element.addEventListener('drop', onWorkspaceDrop);
  });
}

function bindSettingsAutosave() {
  const controls = [
    refs.pixivEnabled,
    refs.pixivUploadMode,
    refs.pixivBrowser,
    refs.pixivVisibility,
    refs.pixivAge,
    refs.pixivSubmitMode,
    refs.pixivTagLanguage,
    refs.pixivSafetyMode,
    refs.pixivProfileDir,
    refs.pixivCookie,
    refs.pixivCsrfToken,
    refs.pixivLlmEnabled,
    refs.pixivLlmImageEnabled,
    refs.pixivLlmBaseUrl,
    refs.pixivLlmApiKey,
    refs.pixivRememberLlmApiKey,
    refs.pixivLlmModelPreset,
    refs.pixivLlmModelCustom,
    refs.pixivLlmTemperature,
    refs.pixivLlmTimeout,
    refs.pixivLlmPromptMetadata,
    refs.pixivLlmPromptImage,
    refs.pixivTitleTemplate,
    refs.pixivTags,
    refs.pixivCaption,
    refs.pixivLockTags,
    refs.pixivUseMetadataTags,
    refs.pixivIncludeLoraTags,
    refs.pixivAddOriginalTag,
    refs.pixivAiGenerated,
    refs.pixivAddUpscaleTag,
    refs.pixivAddEngineTag,
    refs.pixivAddModelTag,
    refs.pixivAddScaleTag,
    refs.batchInputDir,
    refs.batchOutputDir,
  ].filter(Boolean);

  controls.forEach((control) => {
    control.addEventListener('change', scheduleSettingsSave);
    if (control.tagName === 'INPUT' || control.tagName === 'TEXTAREA') {
      const type = String(control.type || '').toLowerCase();
      if (!['checkbox', 'radio', 'range', 'file', 'button', 'submit'].includes(type)) {
        control.addEventListener('input', scheduleSettingsSave);
      }
    }
  });
}

function updatePixivSaveState(message, kind = 'idle') {
  if (!refs.pixivSaveState) {
    return;
  }
  refs.pixivSaveState.textContent = message;
  refs.pixivSaveState.dataset.state = kind;
}

function scheduleSettingsSave() {
  if (!initialized || !window.pywebview?.api) {
    return;
  }
  updatePixivSaveState('等待自动保存…', 'pending');
  if (settingsSaveHandle) {
    window.clearTimeout(settingsSaveHandle);
  }
  settingsSaveHandle = window.setTimeout(() => {
    settingsSaveHandle = null;
    void persistSettingsSilently();
  }, PIXIV_AUTOSAVE_DELAY);
}

async function persistSettingsSilently() {
  if (!initialized || !window.pywebview?.api) {
    return;
  }
  const payload = buildSettings();
  const snapshot = JSON.stringify(payload);
  if (snapshot === state.ui.lastSavedSettingsSnapshot) {
    updatePixivSaveState('配置已是最新状态', 'saved');
    return;
  }
  updatePixivSaveState('等待自动保存…', 'pending');
  try {
    const result = await window.pywebview.api.save_settings(payload);
    if (!result.ok) {
      throw new Error(result.error || '自动保存配置失败');
    }
    state.ui.lastSavedSettingsSnapshot = snapshot;
    if (state.bootstrap && result.config) {
      state.bootstrap.config = result.config;
    }
    updatePixivSaveState('已自动保存', 'saved');
  } catch (error) {
    updatePixivSaveState('自动保存失败，请稍后重试', 'error');
    pushLog(`自动保存配置失败: ${error && error.message ? error.message : error}`);
  }
}

function initSidebarTabs() {
  let saved = 'file';
  try {
    saved = window.localStorage.getItem('imageWorkbench.sidebarPage') || 'file';
  } catch (error) {
    saved = 'file';
  }
  setSidebarPage(saved);
}

function setSidebarPage(page) {
  const next = page || 'file';
  state.ui.sidebarPage = next;

  document.querySelectorAll('.sidebar-tab').forEach((button) => {
    const active = button.dataset.page === next;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', active ? 'true' : 'false');
  });

  document.querySelectorAll('.sidebar-page').forEach((panel) => {
    panel.classList.toggle('is-active', panel.dataset.page === next);
  });

  try {
    window.localStorage.setItem('imageWorkbench.sidebarPage', next);
  } catch (error) {
    // ignore storage failures
  }
}

function hydrateWatermarkFontOptions(items) {
  fillSelect(refs.wmFontPreset, [
    ...(items || []),
    { value: '__custom__', label: '自定义字体文件' },
  ]);
}

function hydrateStaticOptions(data) {
  fillSelect(refs.wmPosition, data.watermarkPositions.map((value) => ({ value, label: value })));
  hydrateWatermarkFontOptions(data.watermarkFonts || []);
  fillSelect(refs.wmSampleMode, data.watermarkSampleModes || []);
  fillSelect(refs.processOrder, data.orderOptions.map((value) => ({ value, label: value })));
  fillSelect(refs.upscaleEngine, Object.entries(data.engines).map(([value, label]) => ({ value, label })));
  fillSelect(refs.pixivUploadMode, data.pixivUploadModeOptions || []);
  fillSelect(refs.pixivBrowser, (data.pixivBrowserChannels || []).map((value) => ({ value, label: value })));
  fillSelect(refs.pixivVisibility, (data.pixivVisibilityOptions || []).map((value) => ({ value, label: value })));
  fillSelect(refs.pixivAge, (data.pixivAgeOptions || []).map((value) => ({ value, label: value })));
  fillSelect(refs.pixivTagLanguage, data.pixivTagLanguageOptions || []);
  fillSelect(refs.pixivSafetyMode, data.pixivSafetyModeOptions || []);
  renderPixivLlmModelOptions([]);
  renderOnlineFontList([]);
  renderRecentDownloadedFonts(data.recentDownloadedFonts || []);
}

function hydrateForm(config) {
  refs.wmEnabled.checked = !!config.watermark.enabled;
  refs.wmText.value = config.watermark.text;
  refs.wmSampleMode.value = config.watermark.sample_mode || 'current';
  applyWatermarkFontSelection(config.watermark.font_path || '');
  refs.wmPosition.value = config.watermark.position;
  refs.wmFontSize.value = config.watermark.font_size;
  refs.wmOpacity.value = config.watermark.opacity;
  refs.wmColor.value = config.watermark.color;
  refs.wmRotMin.value = config.watermark.rotation_min;
  refs.wmRotMax.value = config.watermark.rotation_max;
  refs.wmRandomOffset.checked = !!config.watermark.random_offset;

  refs.mosaicEnabled.checked = !!config.mosaic.enabled;
  refs.mosaicMode.value = config.mosaic.mode;
  refs.mosaicPixelSize.value = config.mosaic.pixel_size;
  refs.mosaicBlurRadius.value = config.mosaic.blur_radius;
  refs.processOrder.value = config.order;

  refs.upscaleEnabled.checked = !!config.upscale.enabled;
  refs.upscaleEngine.value = config.upscale.engine;
  onEngineChange();
  refs.upscaleModel.value = config.upscale.model;
  refs.upscaleCustomModel.value = config.upscale.custom_model_path;
  refs.upscaleScale.value = String(config.upscale.scale);
  refs.upscaleNoise.value = String(config.upscale.noise);

  hydrateBatchForm(config, state.bootstrap?.batch || null);
  hydratePixivForm(config.pixiv || {});
  updateMosaicFieldState();
  syncPixivFieldState();
  renderRecentDownloadedFonts(state.bootstrap?.recentDownloadedFonts || []);
  applyBatchSnapshot(state.bootstrap?.batch || {}, { pushLogs: false });
  state.ui.lastSavedSettingsSnapshot = JSON.stringify(buildSettings());
  updatePixivSaveState('配置改动会自动保存；敏感凭证不会落盘。', 'idle');
}

function fillSelect(select, items) {
  select.innerHTML = '';
  items.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  });
}

function basename(value) {
  return String(value || '').split(/[\\/]/).pop() || '';
}

function getSelectedOptionLabel(select) {
  const option = select?.options?.[select.selectedIndex];
  return option ? option.textContent.trim() : '';
}

function getActiveWatermarkFontValue() {
  return refs.wmFontPreset.value === '__custom__'
    ? String(refs.wmFontPath.value || '').trim()
    : String(refs.wmFontPreset.value || '').trim();
}

function getWatermarkSampleText() {
  const mode = refs.wmSampleMode?.value || 'current';
  const currentText = String(refs.wmText?.value || '').trim();
  const presets = {
    mixed: 'YourName · 龙族助手 Watermark 预览 2026',
    zh: '龙族助手水印预览 · 你好世界',
    en: 'Dragon Watermark Preview · Sample 2026',
  };
  if (mode === 'current') {
    return currentText || DEFAULT_WATERMARK_SAMPLE;
  }
  return presets[mode] || currentText || DEFAULT_WATERMARK_SAMPLE;
}

function updateWatermarkSampleText() {
  if (!refs.wmFontSample) {
    return;
  }
  refs.wmFontSample.textContent = getWatermarkSampleText();
}

function flashFontSelection() {
  if (!refs.fontSampleCard) {
    return;
  }
  refs.fontSampleCard.classList.remove('is-highlighted');
  if (state.ui.fontHighlightTimer) {
    clearTimeout(state.ui.fontHighlightTimer);
  }
  void refs.fontSampleCard.offsetWidth;
  refs.fontSampleCard.classList.add('is-highlighted');
  state.ui.fontHighlightTimer = window.setTimeout(() => {
    refs.fontSampleCard.classList.remove('is-highlighted');
    state.ui.fontHighlightTimer = null;
  }, 1400);
}

function updateWatermarkFontPreview() {
  if (!refs.wmFontPreview) {
    return;
  }

  const selected = refs.wmFontPreset.value;
  const customPath = String(refs.wmFontPath.value || '').trim();
  let preview = '默认：Dancing Script';

  if (selected === '__custom__') {
    preview = customPath ? `自定义：${basename(customPath)}` : '自定义：未选择字体文件';
  } else if (selected) {
    preview = getSelectedOptionLabel(refs.wmFontPreset) || `预设：${basename(selected)}`;
  }

  refs.wmFontPreview.textContent = `当前字体：${preview}`;
  refs.wmFontPreview.title = customPath || selected || '默认：Dancing Script';
}

function renderPixivLlmModelOptions(items) {
  state.ui.pixivLlmModels = Array.isArray(items) ? items : [];
  fillSelect(refs.pixivLlmModelPreset, [
    { value: '', label: '先点击读取模型' },
    ...state.ui.pixivLlmModels,
    { value: '__custom__', label: '自定义模型名' },
  ]);
}

function applyPixivLlmModelSelection(model) {
  const value = String(model || '').trim();
  const matched = Array.from(refs.pixivLlmModelPreset.options).some(
    (option) => option.value === value && value && value !== '__custom__',
  );
  if (!value) {
    refs.pixivLlmModelPreset.value = '';
    refs.pixivLlmModelCustom.value = '';
  } else if (matched) {
    refs.pixivLlmModelPreset.value = value;
    refs.pixivLlmModelCustom.value = '';
  } else {
    refs.pixivLlmModelPreset.value = '__custom__';
    refs.pixivLlmModelCustom.value = value;
  }
  syncPixivLlmModelState();
}

function getActivePixivLlmModelValue() {
  const preset = String(refs.pixivLlmModelPreset.value || '').trim();
  if (preset && preset !== '__custom__') {
    return preset;
  }
  return String(refs.pixivLlmModelCustom.value || '').trim();
}

function syncPixivLlmModelState() {
  const enabled = refs.pixivEnabled.checked;
  const llmEnabled = refs.pixivLlmEnabled.checked;
  const useCustom = refs.pixivLlmModelPreset.value === '__custom__';
  refs.pixivLlmModelPreset.disabled = !enabled || !llmEnabled;
  refs.loadPixivLlmModelsBtn.disabled = !enabled || !llmEnabled;
  refs.pixivLlmModelCustom.disabled = !enabled || !llmEnabled || !useCustom;
}

async function refreshWatermarkFontSample() {
  updateWatermarkSampleText();
  if (!refs.wmFontSample || !window.pywebview || !window.pywebview.api) {
    return;
  }

  const token = ++state.ui.fontPreviewToken;
  refs.wmFontSample.dataset.state = 'loading';
  refs.wmFontSample.style.fontFamily = '';

  try {
    const result = await window.pywebview.api.get_watermark_font_preview(getActiveWatermarkFontValue());
    if (token !== state.ui.fontPreviewToken) {
      return;
    }
    if (!result.ok) {
      throw new Error(result.error || '字体预览加载失败');
    }

    const family = `wm-preview-${token}`;
    const face = new FontFace(family, `url(${result.data_url})`);
    await face.load();
    if (token !== state.ui.fontPreviewToken) {
      return;
    }

    if (state.ui.fontPreviewFace) {
      try {
        document.fonts.delete(state.ui.fontPreviewFace);
      } catch (error) {
        // ignore font cache cleanup failures
      }
    }

    document.fonts.add(face);
    state.ui.fontPreviewFace = face;
    refs.wmFontSample.style.fontFamily = `'${family}', var(--font-display), 'Segoe UI', sans-serif`;
    refs.wmFontSample.dataset.state = 'ready';
    refs.wmFontSample.title = result.path || '字体预览';
  } catch (error) {
    if (token !== state.ui.fontPreviewToken) {
      return;
    }
    refs.wmFontSample.style.fontFamily = '';
    refs.wmFontSample.dataset.state = 'fallback';
    refs.wmFontSample.title = String(error && error.message ? error.message : error);
  }
}

function applyWatermarkFontSelection(fontPath) {
  const value = String(fontPath || '');
  const matched = Array.from(refs.wmFontPreset.options).some((option) => option.value === value);
  if (!value) {
    refs.wmFontPreset.value = '';
  } else if (matched) {
    refs.wmFontPreset.value = value;
  } else {
    refs.wmFontPreset.value = '__custom__';
  }
  refs.wmFontPath.value = value;
  syncWatermarkFontState();
}

function syncWatermarkFontState() {
  const selected = refs.wmFontPreset.value;
  const isCustom = selected === '__custom__';
  refs.wmFontPath.disabled = !isCustom;
  refs.browseFontBtn.disabled = !isCustom;
  if (!isCustom) {
    refs.wmFontPath.value = selected || '';
  }
  updateWatermarkFontPreview();
  void refreshWatermarkFontSample();
}

function onWatermarkFontPresetChange() {
  syncWatermarkFontState();
}

function renderOnlineFontList(items) {
  state.ui.onlineFontItems = Array.isArray(items) ? items : [];
  refs.onlineFontList.innerHTML = '';

  if (!state.ui.onlineFontItems.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '暂无在线字体，请先读取列表';
    refs.onlineFontList.appendChild(option);
    refs.downloadOnlineFontBtn.disabled = true;
    return;
  }

  state.ui.onlineFontItems.forEach((item, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${item.family} · ${item.category || 'uncategorized'} · ${item.variant}`;
    refs.onlineFontList.appendChild(option);
  });
  refs.downloadOnlineFontBtn.disabled = false;
}

function renderRecentDownloadedFonts(items) {
  state.ui.recentDownloadedFonts = Array.isArray(items) ? items : [];
  refs.recentFontList.innerHTML = '';

  if (!state.ui.recentDownloadedFonts.length) {
    const empty = document.createElement('span');
    empty.className = 'hint';
    empty.textContent = '最近还没有下载过在线字体';
    refs.recentFontList.appendChild(empty);
    return;
  }

  state.ui.recentDownloadedFonts.forEach((item) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'recent-font-button';
    button.innerHTML = `${item.family}<span class="meta">${item.variant || ''}</span>`;
    button.title = item.path || item.fileName || item.family;
    button.addEventListener('click', () => {
      applyWatermarkFontSelection(item.path || '');
      updateStatusBadge(`状态: 已切换到字体 ${item.family}`);
      pushLog(`已切换到最近下载字体：${item.family}`);
      flashFontSelection();
    });
    refs.recentFontList.appendChild(button);
  });
}

async function onLoadOnlineFonts() {
  const apiKey = refs.fontApiKey.value.trim();
  const query = refs.fontCatalogQuery.value.trim();
  if (!apiKey) {
    refs.fontCatalogStatus.textContent = '请先填写 Google Fonts API Key';
    updateStatusBadge('状态: 缺少 Google Fonts API Key');
    return;
  }

  refs.loadOnlineFontsBtn.disabled = true;
  refs.fontCatalogStatus.textContent = '正在读取 Google Fonts 列表...';
  try {
    const result = await window.pywebview.api.fetch_google_fonts_catalog(apiKey, query);
    if (!result.ok) {
      throw new Error(result.error || '读取在线字体失败');
    }
    renderOnlineFontList(result.items || []);
    refs.fontCatalogStatus.textContent = result.message || `已读取 ${result.items?.length || 0} 款 Google Fonts 字体`;
    pushLog(refs.fontCatalogStatus.textContent);
    updateStatusBadge('状态: 在线字体列表已更新');
  } catch (error) {
    renderOnlineFontList([]);
    refs.fontCatalogStatus.textContent = String(error && error.message ? error.message : error);
    pushLog(`在线字体列表失败: ${refs.fontCatalogStatus.textContent}`);
    updateStatusBadge('状态: 在线字体列表读取失败');
  } finally {
    refs.loadOnlineFontsBtn.disabled = false;
  }
}

async function onDownloadOnlineFont() {
  const index = Number(refs.onlineFontList.value || -1);
  const item = state.ui.onlineFontItems[index];
  const apiKey = refs.fontApiKey.value.trim();
  if (!item) {
    refs.fontCatalogStatus.textContent = '请先选择要下载的在线字体';
    return;
  }
  if (!apiKey) {
    refs.fontCatalogStatus.textContent = '请先填写 Google Fonts API Key';
    return;
  }

  refs.downloadOnlineFontBtn.disabled = true;
  refs.fontCatalogStatus.textContent = `正在下载：${item.family}`;
  try {
    const result = await window.pywebview.api.download_google_font(apiKey, item.family);
    if (!result.ok) {
      throw new Error(result.error || '下载在线字体失败');
    }
    hydrateWatermarkFontOptions(result.fontOptions || state.bootstrap?.watermarkFonts || []);
    if (state.bootstrap) {
      state.bootstrap.watermarkFonts = result.fontOptions || state.bootstrap.watermarkFonts;
      state.bootstrap.recentDownloadedFonts = result.recentDownloadedFonts || state.bootstrap.recentDownloadedFonts;
    }
    applyWatermarkFontSelection(result.savedPath || '');
    renderRecentDownloadedFonts(result.recentDownloadedFonts || state.ui.recentDownloadedFonts || []);
    flashFontSelection();
    refs.fontCatalogStatus.textContent = result.message || `已下载字体：${item.family}`;
    pushLog(refs.fontCatalogStatus.textContent);
    updateStatusBadge('状态: 在线字体已下载');
  } catch (error) {
    refs.fontCatalogStatus.textContent = String(error && error.message ? error.message : error);
    pushLog(`下载在线字体失败: ${refs.fontCatalogStatus.textContent}`);
    updateStatusBadge('状态: 在线字体下载失败');
  } finally {
    refs.downloadOnlineFontBtn.disabled = !state.ui.onlineFontItems.length;
  }
}

function hydrateBatchForm(config, snapshot) {
  refs.batchInputDir.value = snapshot?.inputDir || config.last_input_dir || '';
  refs.batchOutputDir.value = snapshot?.outputDir || config.last_output_dir || '';
}

function hydratePixivForm(pixiv) {
  refs.pixivEnabled.checked = !!pixiv.enabled;
  ensureSelectValue(refs.pixivUploadMode, pixiv.upload_mode || 'browser');
  ensureSelectValue(refs.pixivBrowser, pixiv.browser_channel || 'msedge');
  ensureSelectValue(refs.pixivVisibility, pixiv.visibility || 'public');
  ensureSelectValue(refs.pixivAge, pixiv.age_restriction || 'all');
  ensureSelectValue(refs.pixivTagLanguage, pixiv.tag_language || 'ja_priority');
  ensureSelectValue(refs.pixivSafetyMode, pixiv.safety_mode || 'auto');
  refs.pixivSubmitMode.value = pixiv.auto_submit ? 'auto' : 'manual';
  refs.pixivProfileDir.value = pixiv.profile_dir || '';
  refs.pixivCookie.value = pixiv.cookie || '';
  refs.pixivCsrfToken.value = pixiv.csrf_token || '';
  refs.pixivLlmEnabled.checked = !!pixiv.llm_enabled;
  refs.pixivLlmImageEnabled.checked = !!pixiv.llm_image_enabled;
  refs.pixivLlmBaseUrl.value = pixiv.llm_base_url || 'https://api.openai.com/v1';
  refs.pixivLlmApiKey.value = pixiv.llm_api_key || '';
  refs.pixivRememberLlmApiKey.checked = !!pixiv.remember_llm_api_key;
  renderPixivLlmModelOptions([]);
  applyPixivLlmModelSelection(pixiv.llm_model || '');
  refs.pixivLlmTemperature.value = String(pixiv.llm_temperature ?? 0.1);
  refs.pixivLlmTimeout.value = String(pixiv.llm_timeout ?? 60);
  refs.pixivLlmPromptMetadata.value = pixiv.llm_metadata_prompt || '';
  refs.pixivLlmPromptImage.value = pixiv.llm_image_prompt || '';
  refs.pixivTitleTemplate.value = pixiv.title_template || '{stem}';
  refs.pixivTags.value = pixiv.tags || '';
  refs.pixivCaption.value = pixiv.caption || '';
  refs.pixivUseMetadataTags.checked = !!pixiv.use_metadata_tags;
  refs.pixivIncludeLoraTags.checked = !!pixiv.include_lora_tags;
  refs.pixivAddOriginalTag.checked = !!pixiv.add_original_tag;
  refs.pixivAiGenerated.checked = !!pixiv.ai_generated;
  refs.pixivAddUpscaleTag.checked = !!pixiv.add_upscale_tag;
  refs.pixivAddEngineTag.checked = !!pixiv.add_engine_tag;
  refs.pixivAddModelTag.checked = !!pixiv.add_model_tag;
  refs.pixivAddScaleTag.checked = !!pixiv.add_scale_tag;
  refs.pixivLockTags.checked = !!pixiv.lock_tags;
}

function ensureSelectValue(select, value) {
  const target = String(value ?? '');
  const exists = Array.from(select.options).some((option) => option.value === target);
  if (!exists && target) {
    const option = document.createElement('option');
    option.value = target;
    option.textContent = target;
    select.appendChild(option);
  }
  select.value = target;
}

function onEngineChange() {
  const engine = refs.upscaleEngine.value || 'realesrgan';
  const models = state.bootstrap.models[engine] || [];
  const scales = state.bootstrap.scaleOptions[engine] || [4];

  fillSelect(refs.upscaleModel, models.map((value) => ({ value, label: value })));
  fillSelect(refs.upscaleScale, scales.map((value) => ({ value: String(value), label: `${value}x` })));

  const isRealEsrgan = engine === 'realesrgan';
  refs.upscaleCustomModel.disabled = !isRealEsrgan;
  refs.browseModelBtn.disabled = !isRealEsrgan;

  const showNoise = engine === 'realcugan';
  refs.upscaleNoise.disabled = !showNoise;
}

function updateMosaicFieldState() {
  const mode = refs.mosaicMode.value;
  refs.mosaicPixelSize.disabled = mode !== 'pixelate';
  refs.mosaicBlurRadius.disabled = mode !== 'blur';
}

function updateRecentImages(items) {
  state.recentImages = Array.isArray(items) ? items : [];
  renderRecentImages();
}

function renderRecentImages() {
  refs.recentList.innerHTML = '';
  if (!state.recentImages.length) {
    const empty = document.createElement('div');
    empty.className = 'recent-item empty';
    empty.innerHTML = '<strong>还没有最近记录</strong><span>选一次图片后，这里会保留最近 8 张，方便快速回到工作现场。</span>';
    refs.recentList.appendChild(empty);
    return;
  }

  state.recentImages.forEach((item, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'recent-item';
    button.innerHTML = `<strong>${escapeHtml(item.fileName)}</strong><span>#${index + 1} · ${escapeHtml(item.parent)}</span>`;
    button.addEventListener('click', () => {
      void loadImagePath(item.path, '从最近记录加载');
    });
    refs.recentList.appendChild(button);
  });
}

async function onOpenImage() {
  const result = await window.pywebview.api.open_image_dialog();
  handleLoadResult(result, '手动选择');
}

async function loadImagePath(path, sourceLabel = '载入图片') {
  updateStatusBadge('状态: 正在加载图片');
  const result = await window.pywebview.api.open_image_path(path);
  handleLoadResult(result, sourceLabel);
}

async function loadImageFile(file, sourceLabel = '拖拽载入') {
  if (!file) {
    pushLog('没有可读取的拖拽文件');
    updateStatusBadge('状态: 拖拽载入失败');
    return;
  }

  const filePath = String(file.path || '').trim();
  if (filePath) {
    await loadImagePath(filePath, sourceLabel);
    return;
  }

  updateStatusBadge('状态: 正在读取拖拽图片');
  try {
    const dataUrl = await fileToDataUrl(file);
    const result = await window.pywebview.api.open_image_blob(file.name || 'dropped-image', dataUrl);
    handleLoadResult(result, `${sourceLabel}（兼容模式）`);
  } catch (error) {
    pushLog(`拖拽载入失败: ${error?.message || error}`);
    updateStatusBadge('状态: 拖拽载入失败');
  }
}

function handleLoadResult(result, sourceLabel) {
  if (!result.ok) {
    if (!result.cancelled) {
      pushLog(result.error || '加载图片失败');
      updateStatusBadge('状态: 载入失败');
    }
    return;
  }

  state.regions = [];
  renderRegionChips();
  updateSource(result.source);
  updatePreview(result.preview || result.source);
  updateRecentImages(result.recentImages || state.recentImages);
  updateStatusBadge(`状态: ${result.message}`);
  pushLog(`${sourceLabel}: ${result.message}`);
}

async function onBrowseFont() {
  const result = await window.pywebview.api.choose_font_dialog();
  if (result.ok) {
    refs.wmFontPreset.value = '__custom__';
    refs.wmFontPath.value = result.path;
    syncWatermarkFontState();
    pushLog(`已选择水印字体：${result.path}`);
  }
}

async function onBrowseModel() {
  const result = await window.pywebview.api.choose_model_dialog();
  if (result.ok) {
    refs.upscaleCustomModel.value = result.path;
    pushLog(`已选择本地权重：${result.path}`);
  }
}

async function onBrowseDirectory(targetRef, label) {
  const result = await window.pywebview.api.choose_directory_dialog(targetRef.value.trim());
  if (result.ok) {
    targetRef.value = result.path;
    pushLog(`${label}：${result.path}`);
  }
}

async function onLoadPixivLlmModels() {
  refs.loadPixivLlmModelsBtn.disabled = true;
  updateStatusBadge('状态: 正在读取提供商模型列表');
  try {
    const result = await window.pywebview.api.fetch_pixiv_llm_models({ pixiv: readPixivSettings() });
    if (!result.ok) {
      throw new Error(result.error || '读取模型列表失败');
    }
    renderPixivLlmModelOptions(result.items || []);
    applyPixivLlmModelSelection(result.selected || getActivePixivLlmModelValue());
    pushLog(result.message || `已读取 ${result.items?.length || 0} 个模型`);
    updateStatusBadge(result.message || '状态: 已更新模型列表');
  } catch (error) {
    pushLog(`读取 Pixiv LLM 模型失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: 读取模型列表失败');
  } finally {
    syncPixivFieldState();
  }
}

async function onTestPixivLlm() {
  refs.testPixivLlmBtn.disabled = true;
  updateStatusBadge('Status: Testing Pixiv LLM');
  const result = await window.pywebview.api.test_pixiv_llm({ pixiv: readPixivSettings() });
  if (!result.ok) {
    pushLog(result.error || 'Pixiv LLM test failed');
    updateStatusBadge('Status: Pixiv LLM test failed');
    syncPixivFieldState();
    return;
  }

  (result.infos || []).forEach((message) => pushLog(`[Pixiv LLM] ${message}`));
  (result.warnings || []).forEach((message) => pushLog(`[Pixiv LLM] ${message}`));
  if ((result.metadataTags || []).length) {
    pushLog(`[Pixiv LLM] Metadata tags: ${result.metadataTags.join(', ')}`);
  }
  if ((result.imageTags || []).length) {
    pushLog(`[Pixiv LLM] Image tags: ${result.imageTags.join(', ')}`);
  }
  pushLog(`[Pixiv LLM] Combined tags: ${(result.tags || []).join(', ')}`);
  updateStatusBadge(`Status: ${result.message}`);
  syncPixivFieldState();
}

async function onStartBatch() {
  const batch = readBatchSettings();
  if (!batch.input_dir || !batch.output_dir) {
    pushLog('请先填写批量输入目录和输出目录');
    updateStatusBadge('状态: 批量任务缺少目录');
    return;
  }

  refs.startBatchBtn.disabled = true;
  refs.stopBatchBtn.disabled = true;
  updateStatusBadge('状态: 正在提交批量任务');
  refs.batchStatusText.textContent = '正在提交批量任务';
  refs.batchCurrentFile.textContent = '等待后台开始处理';
  refs.batchProgressFill.style.width = '0%';

  const result = await window.pywebview.api.start_batch(buildSettings());
  if (!result.ok) {
    refs.startBatchBtn.disabled = false;
    refs.stopBatchBtn.disabled = true;
    pushLog(result.error || '批量任务创建失败');
    updateStatusBadge('状态: 批量任务创建失败');
    refs.batchStatusText.textContent = '创建失败';
    return;
  }

  applyBatchSnapshot(result);
}

async function onStopBatch() {
  if (!state.batch.jobId || !window.pywebview?.api) {
    return;
  }
  refs.stopBatchBtn.disabled = true;
  updateStatusBadge('状态: 正在请求停止批量任务');
  try {
    const result = await window.pywebview.api.stop_batch();
    if (!result.ok) {
      throw new Error(result.error || '停止批量任务失败');
    }
    applyBatchSnapshot(result);
    pushLog(result.message || '已请求停止批量任务');
  } catch (error) {
    refs.stopBatchBtn.disabled = false;
    pushLog(`停止批量任务失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: 停止批量任务失败');
  }
}

async function onRenderPreview() {
  if (!state.source) {
    pushLog('请先选择图片');
    return;
  }

  updateStatusBadge('状态: 正在生成预览');
  const result = await window.pywebview.api.render_preview(buildSettings());
  if (!result.ok) {
    pushLog(result.error || '预览失败');
    updateStatusBadge('状态: 预览失败');
    return;
  }

  updateSource(result.source);
  updatePreview(result.preview);
  (result.logs || []).forEach(pushLog);
  updateStatusBadge(`状态: ${result.message}`);
}

async function onExport() {
  if (!state.source) {
    pushLog('请先选择图片');
    return;
  }

  updateStatusBadge('状态: 正在导出');
  const result = await window.pywebview.api.export_result(buildSettings());
  if (!result.ok) {
    if (!result.cancelled) {
      pushLog(result.error || '导出失败');
      updateStatusBadge('状态: 导出失败');
    }
    return;
  }

  if (result.preview) {
    updatePreview(result.preview);
  }
  (result.logs || []).forEach(pushLog);
  updateStatusBadge(`状态: ${result.message}`);
}

async function onResetPreview() {
  const result = await window.pywebview.api.reset_preview();
  if (!result.ok) {
    pushLog(result.error || '恢复失败');
    return;
  }
  updatePreview(result.preview);
  updateStatusBadge(`状态: ${result.message}`);
  pushLog(result.message);
}

function readBatchSettings() {
  return {
    input_dir: refs.batchInputDir.value.trim(),
    output_dir: refs.batchOutputDir.value.trim(),
  };
}

function readPixivSettings() {
  return {
    enabled: refs.pixivEnabled.checked,
    upload_mode: refs.pixivUploadMode.value,
    browser_channel: refs.pixivBrowser.value,
    visibility: refs.pixivVisibility.value,
    age_restriction: refs.pixivAge.value,
    auto_submit: refs.pixivSubmitMode.value === 'auto',
    tag_language: refs.pixivTagLanguage.value,
    safety_mode: refs.pixivSafetyMode.value,
    profile_dir: refs.pixivProfileDir.value.trim(),
    cookie: refs.pixivCookie.value.trim(),
    csrf_token: refs.pixivCsrfToken.value.trim(),
    llm_enabled: refs.pixivLlmEnabled.checked,
    llm_image_enabled: refs.pixivLlmImageEnabled.checked,
    llm_base_url: refs.pixivLlmBaseUrl.value.trim(),
    llm_api_key: refs.pixivLlmApiKey.value.trim(),
    remember_llm_api_key: refs.pixivRememberLlmApiKey.checked,
    llm_model: getActivePixivLlmModelValue(),
    llm_temperature: Number.parseFloat(refs.pixivLlmTemperature.value || '0.1'),
    llm_timeout: Number.parseInt(refs.pixivLlmTimeout.value || '60', 10),
    llm_metadata_prompt: refs.pixivLlmPromptMetadata.value,
    llm_image_prompt: refs.pixivLlmPromptImage.value,
    title_template: refs.pixivTitleTemplate.value.trim(),
    tags: refs.pixivTags.value,
    caption: refs.pixivCaption.value,
    use_metadata_tags: refs.pixivUseMetadataTags.checked,
    include_lora_tags: refs.pixivIncludeLoraTags.checked,
    add_original_tag: refs.pixivAddOriginalTag.checked,
    ai_generated: refs.pixivAiGenerated.checked,
    add_upscale_tag: refs.pixivAddUpscaleTag.checked,
    add_engine_tag: refs.pixivAddEngineTag.checked,
    add_model_tag: refs.pixivAddModelTag.checked,
    add_scale_tag: refs.pixivAddScaleTag.checked,
    lock_tags: refs.pixivLockTags.checked,
  };
}

function updatePixivModeHint() {
  const enabled = refs.pixivEnabled.checked;
  const directMode = refs.pixivUploadMode.value === 'direct';
  const llmEnabled = refs.pixivLlmEnabled.checked;
  const llmImageEnabled = refs.pixivLlmImageEnabled.checked;
  if (!enabled) {
    refs.pixivModeHint.textContent = '自动标签会受到 Pixiv 当前 10 个标签上限的约束。启用后再决定是走浏览器确认，还是用 Cookie + CSRF 直传。';
    return;
  }
  let message = directMode
    ? '当前是 Cookie + CSRF 直传模式，会直接向 Pixiv 提交请求；即使你选择了手动确认，也不会停留在网页投稿页。'
    : '当前是浏览器自动填写模式。手动投稿时，浏览器会停在投稿页，方便你确认标题、标签和说明是否符合预期。';
  if (llmEnabled && llmImageEnabled) {
    message += ' 当前流程会先做看图打标，再把看图结果和 metadata 一起送去 OpenAI-compatible 接口生成最终 Pixiv 标签。';
  } else if (llmEnabled) {
    message += ' 当前启用了 LLM 综合润色，metadata 提示词会送去 OpenAI-compatible 接口整理成 Pixiv 风格标签。';
  }
  if (refs.pixivSafetyMode.value === 'strict') {
    message += ' 当前启用了严格拦截，命中 NSFW 或幼态高风险标签时不会自动投稿。';
  } else if (refs.pixivSafetyMode.value === 'auto') {
    message += ' 当前启用了自动安全护栏，命中成人/猎奇标签会自动提升到 R-18 / R-18G，并拦截高风险未成年性化组合。';
  }
  refs.pixivModeHint.textContent = message;
}

function syncPixivFieldState() {
  const enabled = refs.pixivEnabled.checked;
  const directMode = refs.pixivUploadMode.value === 'direct';
  const llmEnabled = refs.pixivLlmEnabled.checked;
  const llmImageEnabled = refs.pixivLlmImageEnabled.checked;
  const credentialSupported = state.bootstrap?.supportsCredentialStorage !== false;
  [
    refs.pixivUploadMode,
    refs.pixivVisibility,
    refs.pixivAge,
    refs.pixivSubmitMode,
    refs.pixivTagLanguage,
    refs.pixivSafetyMode,
    refs.pixivLlmEnabled,
    refs.pixivLlmImageEnabled,
    refs.pixivTitleTemplate,
    refs.pixivTags,
    refs.pixivCaption,
    refs.pixivUseMetadataTags,
    refs.pixivIncludeLoraTags,
    refs.pixivAddOriginalTag,
    refs.pixivAiGenerated,
    refs.pixivAddUpscaleTag,
    refs.pixivAddEngineTag,
    refs.pixivAddModelTag,
    refs.pixivAddScaleTag,
    refs.pixivLockTags,
  ].forEach((element) => {
    element.disabled = !enabled;
  });
  refs.pixivBrowser.disabled = !enabled || directMode;
  refs.pixivProfileDir.disabled = !enabled || directMode;
  refs.browsePixivProfileBtn.disabled = !enabled || directMode;
  refs.pixivCookie.disabled = !enabled || !directMode;
  refs.pixivCsrfToken.disabled = !enabled || !directMode;
  refs.pixivLlmImageEnabled.disabled = !enabled || !llmEnabled;
  refs.pixivLlmBaseUrl.disabled = !enabled || !llmEnabled;
  refs.pixivLlmApiKey.disabled = !enabled || !llmEnabled;
  refs.pixivRememberLlmApiKey.disabled = !enabled || !llmEnabled || !credentialSupported;
  refs.pixivRememberLlmApiKey.title = credentialSupported ? '' : 'Windows Credential Manager is not available in this environment';
  syncPixivLlmModelState();
  refs.pixivLlmTemperature.disabled = !enabled || !llmEnabled;
  refs.pixivLlmTimeout.disabled = !enabled || !llmEnabled;
  refs.pixivLlmPromptMetadata.disabled = !enabled || !llmEnabled;
  refs.pixivLlmPromptImage.disabled = !enabled || !llmEnabled;
  refs.testPixivLlmBtn.disabled = !enabled || !llmEnabled;
  updatePixivModeHint();
}

function updateBatchButton(running, cancelRequested = false) {
  refs.startBatchBtn.disabled = !!running;
  refs.stopBatchBtn.disabled = !running || !!cancelRequested;
  refs.startBatchBtn.textContent = running ? '批量处理中...' : '开始批量处理';
  refs.stopBatchBtn.textContent = cancelRequested ? '停止中...' : '停止处理';
}

function applyBatchSnapshot(snapshot, options = {}) {
  const safe = snapshot || {};
  const processed = Number(safe.processed || 0);
  const total = Number(safe.total || 0);
  const errors = Number(safe.errors || 0);
  const successes = Number(safe.successes || 0);
  const running = !!safe.running;
  const completed = !!safe.completed;
  const cancelRequested = !!safe.cancelRequested;
  const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  refs.batchStatusText.textContent = safe.status || '未开始';
  refs.batchProgressLabel.textContent = `${processed} / ${total}`;
  refs.batchProgressFill.style.width = `${percent}%`;
  refs.batchCurrentFile.textContent = safe.currentFile || (running ? (cancelRequested ? '停止请求已发送，等待当前图片完成' : '正在等待下一张图片') : '等待任务开始；停止会在当前图片完成后生效');
  refs.batchSummary.textContent = `成功 ${successes} · 错误 ${errors}`;

  state.batch.jobId = Number(safe.jobId || 0);
  state.batch.nextOffset = Number(safe.nextOffset || 0);

  if (options.pushLogs !== false) {
    (safe.logs || []).forEach(pushLog);
  }

  updateBatchButton(running, cancelRequested);
  if (running) {
    updateStatusBadge(`状态: ${safe.status || '批量处理中'}`);
    startBatchPolling();
  } else {
    if (completed || state.batch.jobId) {
      updateStatusBadge(`状态: ${safe.status || '批量处理已结束'}`);
    }
    stopBatchPolling();
  }
}

function startBatchPolling() {
  if (batchPollHandle) {
    return;
  }
  batchPollHandle = window.setInterval(() => {
    void pollBatchStatus();
  }, 1200);
  void pollBatchStatus();
}

function stopBatchPolling() {
  if (batchPollHandle) {
    window.clearInterval(batchPollHandle);
    batchPollHandle = null;
  }
}

async function pollBatchStatus() {
  if (!state.batch.jobId || state.batch.polling || !window.pywebview?.api) {
    return;
  }

  state.batch.polling = true;
  try {
    const result = await window.pywebview.api.poll_batch_status(state.batch.nextOffset || 0);
    if (!result.ok) {
      throw new Error(result.error || '轮询批量状态失败');
    }
    applyBatchSnapshot(result);
  } catch (error) {
    stopBatchPolling();
    pushLog(`批量状态轮询失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: 批量状态轮询失败');
  } finally {
    state.batch.polling = false;
  }
}

function updateSource(payload) {
  state.source = payload;
  refs.currentFile.textContent = payload.fileName;
  refs.currentFile.title = payload.path || payload.fileName;
  refs.sourceMeta.textContent = `${payload.fileName} · ${payload.width} x ${payload.height}`;
  refs.badgeSourceSize.textContent = `源图: ${payload.width} x ${payload.height}`;
  refs.sourceImage.src = payload.src;
  refs.sourceImage.onload = () => {
    refs.sourceStage.classList.add('active');
    refs.sourceEmpty.classList.add('hidden');
    renderRegions();
  };
}

function updatePreview(payload) {
  state.preview = payload;
  refs.resultMeta.textContent = `${payload.fileName} · ${payload.width} x ${payload.height}`;
  refs.badgePreviewSize.textContent = `结果: ${payload.width} x ${payload.height}`;
  refs.resultImage.src = payload.src;
  refs.resultImage.onload = () => {
    refs.resultStage.classList.add('active');
    refs.resultEmpty.classList.add('hidden');
  };
}

function buildSettings() {
  return {
    order: refs.processOrder.value,
    regions: state.regions,
    watermark: {
      enabled: refs.wmEnabled.checked,
      text: refs.wmText.value,
      sample_mode: refs.wmSampleMode.value,
      font_path: refs.wmFontPreset.value && refs.wmFontPreset.value !== '__custom__'
        ? refs.wmFontPreset.value
        : refs.wmFontPath.value.trim(),
      position: refs.wmPosition.value,
      font_size: Number(refs.wmFontSize.value || 48),
      opacity: Number(refs.wmOpacity.value || 0.6),
      color: refs.wmColor.value,
      rotation_min: Number(refs.wmRotMin.value || -10),
      rotation_max: Number(refs.wmRotMax.value || 10),
      random_offset: refs.wmRandomOffset.checked,
    },
    mosaic: {
      enabled: refs.mosaicEnabled.checked,
      mode: refs.mosaicMode.value,
      pixel_size: Number(refs.mosaicPixelSize.value || 10),
      blur_radius: Number(refs.mosaicBlurRadius.value || 15),
    },
    upscale: {
      enabled: refs.upscaleEnabled.checked,
      engine: refs.upscaleEngine.value,
      model: refs.upscaleModel.value,
      custom_model_path: refs.upscaleCustomModel.value.trim(),
      scale: Number(refs.upscaleScale.value || 4),
      noise: Number(refs.upscaleNoise.value || -1),
    },
    batch: readBatchSettings(),
    pixiv: readPixivSettings(),
  };
}

function onSourceMouseDown(event) {
  if (!state.source || event.button !== 0) {
    return;
  }

  const metrics = imageMetrics();
  if (!metrics) {
    return;
  }
  if (!pointInside(event.clientX, event.clientY, metrics.rect)) {
    return;
  }

  state.dragging = true;
  state.dragStart = clampToRect(event.clientX, event.clientY, metrics.rect);
  refs.dragSelection.classList.remove('hidden');
  setDragSelection(state.dragStart.x, state.dragStart.y, state.dragStart.x, state.dragStart.y, metrics);
}

function onSourceMouseMove(event) {
  if (!state.dragging) {
    return;
  }

  const metrics = imageMetrics();
  if (!metrics) {
    return;
  }
  const current = clampToRect(event.clientX, event.clientY, metrics.rect);
  setDragSelection(state.dragStart.x, state.dragStart.y, current.x, current.y, metrics);
}

function onSourceMouseUp(event) {
  if (!state.dragging) {
    return;
  }

  const metrics = imageMetrics();
  refs.dragSelection.classList.add('hidden');
  state.dragging = false;
  if (!metrics) {
    return;
  }

  const end = clampToRect(event.clientX, event.clientY, metrics.rect);
  const region = rectToImageRegion(state.dragStart, end, metrics);
  state.dragStart = null;

  if (!region) {
    return;
  }

  state.regions.push(region);
  renderRegionChips();
  renderRegions();
  updateRegionBadge();
  updateStatusBadge('状态: 选区已更新');
  pushLog(`添加选区: (${region.join(', ')})`);
}

function setDragSelection(x1, y1, x2, y2, metrics) {
  const left = Math.min(x1, x2) - metrics.stageRect.left;
  const top = Math.min(y1, y2) - metrics.stageRect.top;
  const width = Math.abs(x2 - x1);
  const height = Math.abs(y2 - y1);
  refs.dragSelection.style.left = `${left}px`;
  refs.dragSelection.style.top = `${top}px`;
  refs.dragSelection.style.width = `${width}px`;
  refs.dragSelection.style.height = `${height}px`;
}

function renderRegionChips() {
  refs.regionList.innerHTML = '';
  if (!state.regions.length) {
    refs.regionList.innerHTML = '<span class="hint">还没有选区，直接在源图上拖一块出来就行。</span>';
  } else {
    state.regions.forEach((region, index) => {
      const chip = document.createElement('div');
      chip.className = 'region-chip';
      chip.innerHTML = `<span>#${index + 1} ${region.join(', ')}</span>`;

      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '×';
      button.addEventListener('click', () => {
        state.regions.splice(index, 1);
        renderRegionChips();
        renderRegions();
        updateRegionBadge();
      });
      chip.appendChild(button);
      refs.regionList.appendChild(chip);
    });
  }
  updateRegionBadge();
}

function renderRegions() {
  refs.selectionLayer.innerHTML = '';
  if (!state.source || !state.regions.length) {
    return;
  }

  const metrics = imageMetrics();
  if (!metrics) {
    return;
  }

  state.regions.forEach((region, index) => {
    const [x1, y1, x2, y2] = region;
    const box = document.createElement('div');
    box.className = 'selection-box';
    box.dataset.index = String(index + 1);
    box.style.left = `${(x1 / state.source.width) * metrics.rect.width}px`;
    box.style.top = `${(y1 / state.source.height) * metrics.rect.height}px`;
    box.style.width = `${((x2 - x1) / state.source.width) * metrics.rect.width}px`;
    box.style.height = `${((y2 - y1) / state.source.height) * metrics.rect.height}px`;
    refs.selectionLayer.appendChild(box);
  });
}

function imageMetrics() {
  if (!state.source || !refs.sourceImage.complete || !refs.sourceImage.naturalWidth) {
    return null;
  }

  const imgRect = refs.sourceImage.getBoundingClientRect();
  const stageRect = refs.sourceStage.getBoundingClientRect();
  refs.selectionLayer.style.left = `${imgRect.left - stageRect.left}px`;
  refs.selectionLayer.style.top = `${imgRect.top - stageRect.top}px`;
  refs.selectionLayer.style.width = `${imgRect.width}px`;
  refs.selectionLayer.style.height = `${imgRect.height}px`;
  refs.dragSelection.style.left = `${imgRect.left - stageRect.left}px`;
  refs.dragSelection.style.top = `${imgRect.top - stageRect.top}px`;

  return { rect: imgRect, stageRect };
}

function rectToImageRegion(start, end, metrics) {
  const left = Math.min(start.x, end.x);
  const top = Math.min(start.y, end.y);
  const right = Math.max(start.x, end.x);
  const bottom = Math.max(start.y, end.y);

  if (Math.abs(right - left) < 8 || Math.abs(bottom - top) < 8) {
    return null;
  }

  return [
    clampInt(((left - metrics.rect.left) / metrics.rect.width) * state.source.width, 0, state.source.width),
    clampInt(((top - metrics.rect.top) / metrics.rect.height) * state.source.height, 0, state.source.height),
    clampInt(((right - metrics.rect.left) / metrics.rect.width) * state.source.width, 0, state.source.width),
    clampInt(((bottom - metrics.rect.top) / metrics.rect.height) * state.source.height, 0, state.source.height),
  ];
}

function undoLastRegion() {
  if (!state.regions.length) {
    updateStatusBadge('状态: 没有可撤销的选区');
    return;
  }
  const removed = state.regions.pop();
  renderRegionChips();
  renderRegions();
  updateStatusBadge('状态: 已撤销上一个选区');
  pushLog(`撤销选区: (${removed.join(', ')})`);
}

function clearRegions() {
  if (!state.regions.length) {
    updateStatusBadge('状态: 当前没有选区');
    return;
  }
  state.regions = [];
  renderRegionChips();
  renderRegions();
  updateStatusBadge('状态: 选区已清空');
  pushLog('已清空全部选区');
}

function onWorkspaceKeyDown(event) {
  const key = String(event.key || '').toLowerCase();
  const modifier = event.ctrlKey || event.metaKey;
  const tagName = String(event.target?.tagName || '').toLowerCase();
  const isEditing = tagName === 'input' || tagName === 'textarea' || tagName === 'select' || event.target?.isContentEditable;

  if (modifier && key === 'o') {
    event.preventDefault();
    void onOpenImage();
    return;
  }
  if (modifier && key === 'enter') {
    event.preventDefault();
    void onRenderPreview();
    return;
  }
  if (modifier && key === 's') {
    event.preventDefault();
    void onExport();
    return;
  }

  if (isEditing) {
    return;
  }

  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    undoLastRegion();
    return;
  }

  if (event.key === 'Escape') {
    cancelActiveDrag();
    state.dragDepth = 0;
    setDropReady(false);
  }
}

function onWorkspaceDragEnter(event) {
  if (!hasFileTransfer(event)) {
    return;
  }
  event.preventDefault();
  state.dragDepth += 1;
  setDropReady(true);
}

function onWorkspaceDragOver(event) {
  if (!hasFileTransfer(event)) {
    return;
  }
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy';
  }
  setDropReady(true);
}

function onWorkspaceDragLeave(event) {
  if (!hasFileTransfer(event)) {
    return;
  }
  if (event.currentTarget && event.relatedTarget && event.currentTarget.contains(event.relatedTarget)) {
    return;
  }
  state.dragDepth = Math.max(0, state.dragDepth - 1);
  if (state.dragDepth === 0) {
    setDropReady(false);
  }
}

async function onWorkspaceDrop(event) {
  if (!hasFileTransfer(event)) {
    return;
  }
  event.preventDefault();
  state.dragDepth = 0;
  setDropReady(false);

  const files = Array.from(event.dataTransfer?.files || []);
  const imageFile = files.find((file) => isSupportedImagePath(file.path || file.name));
  if (!imageFile) {
    pushLog('拖入的文件不是受支持的图片格式');
    updateStatusBadge('状态: 拖拽文件不受支持');
    return;
  }

  await loadImageFile(imageFile, '拖拽载入');
}

function hasFileTransfer(event) {
  const types = Array.from(event.dataTransfer?.types || []);
  return types.includes('Files');
}

function isSupportedImagePath(value) {
  return /\.(png|jpe?g|webp|bmp)$/i.test(String(value || ''));
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('读取拖拽文件失败'));
    reader.readAsDataURL(file);
  });
}

function cancelActiveDrag() {
  state.dragging = false;
  state.dragStart = null;
  refs.dragSelection.classList.add('hidden');
}

function setDropReady(active) {
  [refs.sourceViewport, refs.resultViewport].forEach((element) => {
    element.classList.toggle('drop-ready', active);
  });
  [refs.sourceDropOverlay, refs.resultDropOverlay].forEach((element) => {
    element.classList.toggle('hidden', !active);
  });
}

function pointInside(x, y, rect) {
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

function clampToRect(x, y, rect) {
  return {
    x: Math.min(Math.max(x, rect.left), rect.right),
    y: Math.min(Math.max(y, rect.top), rect.bottom),
  };
}

function clampInt(value, min, max) {
  return Math.max(min, Math.min(max, Math.round(value)));
}

function updateStatusBadge(text) {
  refs.badgeStatus.textContent = text;
}

function updateRegionBadge() {
  refs.badgeRegionCount.textContent = `选区: ${state.regions.length}`;
}

function showStartupOverlay(title, message) {
  if (!refs.startupOverlay) {
    return;
  }
  refs.startupTitle.textContent = title;
  refs.startupMessage.textContent = message;
  refs.startupOverlay.classList.remove('hidden');
}

function hideStartupOverlay() {
  if (!refs.startupOverlay) {
    return;
  }
  refs.startupOverlay.classList.add('hidden');
}

function pushLog(message) {
  const item = document.createElement('div');
  item.className = 'log-item';
  const time = new Date().toLocaleTimeString();
  item.innerHTML = `<time>${time}</time><p>${escapeHtml(message)}</p>`;
  refs.logList.prepend(item);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}































