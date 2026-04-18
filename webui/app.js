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
    running: false,
    completed: false,
    cancelRequested: false,
    retryMode: false,
    status: '',
    currentFile: '',
    inputDir: '',
    outputDir: '',
    lastError: '',
    failedFiles: [],
  },
  pixivCurrent: {
    jobId: 0,
    nextOffset: 0,
    polling: false,
    running: false,
    completed: false,
    failed: false,
    draftReady: false,
    status: '',
    message: '',
    currentFile: '',
  },
  ui: {
    sidebarPage: 'file',
    compactMode: false,
    logFilter: 'all',
    fontPreviewToken: 0,
    fontPreviewFace: null,
    onlineFontItems: [],
    recentDownloadedFonts: [],
    fontHighlightTimer: null,
    pixivLlmModels: [],
    pixivSessionCookie: '',
    pixivSessionCsrfToken: '',
    pixivCanTestDirect: false,
    lastSavedSettingsSnapshot: '',
    lastExportedPath: '',
    logs: [],
  },
};

const refs = {};
let initialized = false;
let startupFallbackTimer = null;
let batchPollHandle = null;
let pixivCurrentPollHandle = null;
let settingsSaveHandle = null;
const PIXIV_AUTOSAVE_DELAY = 500;
const DEFAULT_WATERMARK_SAMPLE = 'YourName 路 水印预览 2026';
const WIDE_LAYOUT_MIN_DEVICE_PX = 1360;
const PIXIV_TITLE_STYLE_OPTIONS = [
  { value: 'default', label: '默认' },
  { value: 'minimal', label: '简洁' },
  { value: 'dreamy', label: '梦幻' },
  { value: 'light_novel', label: '日系轻小说' },
  { value: 'character_focus', label: '角色中心' },
  { value: 'custom', label: '自定义' },
];
const PIXIV_TITLE_STYLE_PROMPTS = {
  default: '',
  minimal: 'Keep the title concise, clean, and elegant. Prefer 6-16 characters when possible. Avoid ornate wording.',
  dreamy: 'Polish the title into a soft, dreamy, delicate style suitable for atmospheric fantasy illustrations.',
  light_novel: 'Polish the title into a light-novel-like Japanese illustration title. Keep it catchy but not overly long.',
  character_focus: 'Make the title focus on the character impression, mood, and visual identity. Keep it natural and searchable for Pixiv.',
  custom: '',
};

window.addEventListener('pywebviewready', maybeInit);
window.addEventListener('DOMContentLoaded', maybeInit);
window.addEventListener('resize', () => {
  updateViewportLayoutMode();
  renderRegions();
});

if (document.readyState === 'complete' || document.readyState === 'interactive') {
  window.setTimeout(maybeInit, 0);
}

function updateViewportLayoutMode() {
  if (!document.body) {
    return;
  }
  const cssWidth = Math.max(
    window.innerWidth || 0,
    document.documentElement?.clientWidth || 0,
  );
  const deviceScale = window.devicePixelRatio || 1;
  const effectiveWidth = cssWidth * deviceScale;
  const wide = effectiveWidth >= WIDE_LAYOUT_MIN_DEVICE_PX;
  document.body.classList.toggle('layout-wide', wide);
  document.body.classList.toggle('layout-narrow', !wide);
}

function maybeInit() {
  cacheRefs();
  updateViewportLayoutMode();
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
  showStartupOverlay('正在同步工作台状态', '正在读取最近图片、批量状态和 Pixiv 配置。', '阶段 2 / 3：同步配置');

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
  initUiPreferences();
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
    'startupProgress',
    'sidebarTabbar',
    'currentFile',
    'recentList',
    'quickStartGuide',
    'quickGuideTitle',
    'quickGuideLead',
    'quickGuideSteps',
    'quickGuidePrimaryBtn',
    'quickGuideSecondaryBtn',
    'quickGuideHint',
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
    'openBatchInputDirBtn',
    'openBatchOutputDirBtn',
    'viewBatchErrorsBtn',
    'batchActionHint',
    'retryFailedBatchBtn',
    'batchStatusText',
    'batchProgressLabel',
    'batchProgressFill',
    'batchCurrentFile',
    'batchSummary',
    'batchRecoveryCard',
    'batchLastError',
    'batchFailedFiles',
    'pixivEnabled',
    'pixivUploadMode',
    'pixivBrowser',
    'pixivVisibility',
    'pixivAge',
    'pixivSexualDepiction',
    'pixivSubmitMode',
    'pixivTagLanguage',
    'pixivSafetyMode',
    'pixivProfileDir',
    'browsePixivProfileBtn',
    'pixivCookie',
    'pixivCsrfToken',
    'importPixivAuthBtn',
    'testPixivDirectBtn',
    'pixivDirectStatus',
    'pixivLlmEnabled',
    'pixivLlmImageEnabled',
    'pixivLlmTitleEnabled',
    'pixivLlmTitleStyle',
    'resetPixivTitlePromptBtn',
    'pixivLlmBaseUrl',
    'pixivLlmApiKey',
    'pixivRememberLlmApiKey',
    'loadPixivLlmModelsBtn',
    'testPixivLlmBtn',
    'previewPixivBtn',
    'testPixivUploadBtn',
    'capturePixivDebugBtn',
    'pixivLlmModelPreset',
    'pixivLlmModelCustom',
    'pixivLlmTemperature',
    'pixivLlmTimeout',
    'pixivLlmPromptMetadata',
    'pixivLlmPromptImage',
    'pixivLlmPromptTitle',
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
    'quickPixivUploadBtn',
    'quickActionHint',
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
    'copyLogBtn',
    'exportLogBtn',
    'clearLogBtn',
    'compactModeBtn',
  ];

  ids.forEach((id) => {
    refs[id] = document.getElementById(id);
  });
}

function bindEvents() {
  const on = (element, eventName, handler) => {
    element?.addEventListener(eventName, handler);
  };

  on(refs.openImageBtn, 'click', onOpenImage);
  on(refs.quickGuidePrimaryBtn, 'click', onQuickGuideAction);
  on(refs.quickGuideSecondaryBtn, 'click', onQuickGuideAction);
  on(refs.browseFontBtn, 'click', onBrowseFont);
  on(refs.browseModelBtn, 'click', onBrowseModel);
  on(refs.browseBatchInputBtn, 'click', () => {
    void onBrowseDirectory(refs.batchInputDir, '宸查€夋嫨鎵归噺杈撳叆鐩綍');
  });
  on(refs.browseBatchOutputBtn, 'click', () => {
    void onBrowseDirectory(refs.batchOutputDir, '宸查€夋嫨鎵归噺杈撳嚭鐩綍');
  });
  on(refs.browsePixivProfileBtn, 'click', () => {
    void onBrowseDirectory(refs.pixivProfileDir, '宸查€夋嫨 Pixiv 资料目录');
  });
  [refs.batchInputDir, refs.batchOutputDir].forEach((control) => {
    control?.addEventListener('input', updateBatchRecovery);
    control?.addEventListener('change', updateBatchRecovery);
  });
  on(refs.pixivUploadMode, 'change', syncPixivFieldState);
  on(refs.pixivSubmitMode, 'change', updatePixivModeHint);
  on(refs.pixivSexualDepiction, 'change', updatePixivModeHint);
  on(refs.pixivSafetyMode, 'change', updatePixivModeHint);
  on(refs.pixivLlmEnabled, 'change', syncPixivFieldState);
  on(refs.pixivLlmImageEnabled, 'change', updatePixivModeHint);
  on(refs.pixivLlmTitleEnabled, 'change', updatePixivModeHint);
  on(refs.pixivLlmTitleStyle, 'change', () => {
    syncPixivTitlePromptPresetState();
    syncPixivTitleStyleFromPrompt();
    scheduleSettingsSave();
    refreshExperienceUi();
  });
  on(refs.pixivLlmPromptTitle, 'input', () => {
    syncPixivTitleStyleFromPrompt();
  });
  on(refs.resetPixivTitlePromptBtn, 'click', resetPixivTitlePromptToPreset);
  on(refs.pixivLlmModelPreset, 'change', syncPixivLlmModelState);
  on(refs.loadPixivLlmModelsBtn, 'click', onLoadPixivLlmModels);
  on(refs.testPixivLlmBtn, 'click', onTestPixivLlm);
  on(refs.previewPixivBtn, 'click', onPreviewPixivSubmission);
  on(refs.testPixivUploadBtn, 'click', onTestPixivUploadCurrent);
  on(refs.capturePixivDebugBtn, 'click', onCapturePixivDebug);
  on(refs.importPixivAuthBtn, 'click', onImportPixivBrowserAuth);
  on(refs.testPixivDirectBtn, 'click', onTestPixivDirect);
  on(refs.startBatchBtn, 'click', () => {
    void onStartBatch();
  });
  on(refs.stopBatchBtn, 'click', () => {
    void onStopBatch();
  });
  on(refs.retryFailedBatchBtn, 'click', () => {
    void onRetryFailedBatch();
  });
  on(refs.renderPreviewBtn, 'click', () => {
    void onRenderPreview();
  });
  on(refs.quickPixivUploadBtn, 'click', () => {
    void onTestPixivUploadCurrent();
  });
  on(refs.exportBtn, 'click', onExport);
  on(refs.resetPreviewBtn, 'click', onResetPreview);
  on(refs.undoRegionBtn, 'click', undoLastRegion);
  on(refs.clearRegionsBtn, 'click', clearRegions);
  on(refs.copyLogBtn, 'click', onCopyLogs);
  on(refs.exportLogBtn, 'click', onExportLogs);
  on(refs.clearLogBtn, 'click', () => {
    state.ui.logs = [];
    if (refs.logList) {
      refs.logList.innerHTML = '';
    }
    updateStatusBadge('状态: 日志已清空');
  });
  document.querySelectorAll('.sidebar-tab').forEach((button) => {
    button.addEventListener('click', () => {
      setSidebarPage(button.dataset.page || 'file');
    });
  });
  on(refs.compactModeBtn, 'click', toggleCompactMode);
  document.querySelectorAll('[data-log-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      setLogFilter(button.dataset.logFilter || 'all');
    });
  });
  document.querySelectorAll('.fold-card[id]').forEach((details) => {
    details.addEventListener('toggle', () => {
      saveFoldState(details.id, details.open);
    });
  });
  on(refs.wmFontPreset, 'change', onWatermarkFontPresetChange);
  on(refs.wmFontPath, 'input', updateWatermarkFontPreview);
  on(refs.wmFontPath, 'change', syncWatermarkFontState);
  on(refs.wmText, 'input', updateWatermarkSampleText);
  on(refs.wmSampleMode, 'change', updateWatermarkSampleText);
  on(refs.loadOnlineFontsBtn, 'click', onLoadOnlineFonts);
  bindSettingsAutosave();
  on(refs.downloadOnlineFontBtn, 'click', onDownloadOnlineFont);
  document.querySelectorAll('[data-font-query]').forEach((button) => {
    button.addEventListener('click', () => {
      refs.fontCatalogQuery.value = button.dataset.fontQuery || '';
      void onLoadOnlineFonts();
    });
  });
  on(refs.upscaleEngine, 'change', onEngineChange);
  on(refs.mosaicMode, 'change', updateMosaicFieldState);
  on(refs.pixivEnabled, 'change', syncPixivFieldState);
  [refs.wmEnabled, refs.mosaicEnabled, refs.upscaleEnabled].forEach((control) => {
    control?.addEventListener('change', refreshExperienceUi);
  });
  on(refs.sourceStage, 'mousedown', onSourceMouseDown);
  window.addEventListener('mousemove', onSourceMouseMove);
  window.addEventListener('mouseup', onSourceMouseUp);
  window.addEventListener('keydown', onWorkspaceKeyDown);
  window.addEventListener('beforeunload', () => {
    stopBatchPolling();
    stopPixivCurrentPolling();
  });

  [refs.sourceViewport, refs.resultViewport].forEach((element) => {
    on(element, 'dragenter', onWorkspaceDragEnter);
    on(element, 'dragover', onWorkspaceDragOver);
    on(element, 'dragleave', onWorkspaceDragLeave);
    on(element, 'drop', onWorkspaceDrop);
  });
}

function bindSettingsAutosave() {
  const controls = [
    refs.pixivEnabled,
    refs.pixivUploadMode,
    refs.pixivBrowser,
    refs.pixivVisibility,
    refs.pixivAge,
    refs.pixivSexualDepiction,
    refs.pixivSubmitMode,
    refs.pixivTagLanguage,
    refs.pixivSafetyMode,
    refs.pixivProfileDir,
    refs.pixivCookie,
    refs.pixivCsrfToken,
    refs.pixivLlmEnabled,
    refs.pixivLlmImageEnabled,
    refs.pixivLlmTitleEnabled,
    refs.pixivLlmTitleStyle,
    refs.pixivLlmBaseUrl,
    refs.pixivLlmApiKey,
    refs.pixivRememberLlmApiKey,
    refs.pixivLlmModelPreset,
    refs.pixivLlmModelCustom,
    refs.pixivLlmTemperature,
    refs.pixivLlmTimeout,
    refs.pixivLlmPromptMetadata,
    refs.pixivLlmPromptImage,
    refs.pixivLlmPromptTitle,
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
    control.addEventListener('change', refreshExperienceUi);
    if (control.tagName === 'INPUT' || control.tagName === 'TEXTAREA') {
      const type = String(control.type || '').toLowerCase();
      if (!['checkbox', 'radio', 'range', 'file', 'button', 'submit'].includes(type)) {
        control.addEventListener('input', scheduleSettingsSave);
        control.addEventListener('input', refreshExperienceUi);
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

function updatePixivDirectStatus(message, kind = 'idle') {
  if (!refs.pixivDirectStatus) {
    return;
  }
  refs.pixivDirectStatus.textContent = message;
  refs.pixivDirectStatus.dataset.state = kind;
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
    updatePixivSaveState('配置已经是最新状态', 'saved');
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

function initUiPreferences() {
  let compactMode = false;
  let logFilter = 'all';
  try {
    compactMode = window.localStorage.getItem('imageWorkbench.compactMode') === 'true';
    logFilter = window.localStorage.getItem('imageWorkbench.logFilter') || 'all';
  } catch (error) {
    compactMode = false;
    logFilter = 'all';
  }
  applyCompactMode(compactMode);
  restoreFoldStates();
  setLogFilter(logFilter);
}

function applyCompactMode(enabled) {
  const active = !!enabled;
  state.ui.compactMode = active;
  document.body.classList.toggle('density-compact', active);
  if (refs.compactModeBtn) {
    refs.compactModeBtn.textContent = active ? '紧凑模式：开' : '紧凑模式：关';
    refs.compactModeBtn.dataset.state = active ? 'compact' : 'comfortable';
  }
  try {
    window.localStorage.setItem('imageWorkbench.compactMode', active ? 'true' : 'false');
  } catch (error) {
    // ignore storage failures
  }
}

function toggleCompactMode() {
  applyCompactMode(!state.ui.compactMode);
}

function saveFoldState(id, open) {
  try {
    window.localStorage.setItem(`imageWorkbench.fold.${id}`, open ? 'true' : 'false');
  } catch (error) {
    // ignore storage failures
  }
}

function restoreFoldStates() {
  document.querySelectorAll('.fold-card[id]').forEach((details) => {
    try {
      const saved = window.localStorage.getItem(`imageWorkbench.fold.${details.id}`);
      if (saved !== null) {
        details.open = saved === 'true';
      }
    } catch (error) {
      // ignore storage failures
    }
  });
}

function setLogFilter(filter) {
  const next = ['all', 'task', 'pixiv', 'error'].includes(filter) ? filter : 'all';
  state.ui.logFilter = next;
  document.querySelectorAll('[data-log-filter]').forEach((button) => {
    const active = (button.dataset.logFilter || 'all') === next;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  try {
    window.localStorage.setItem('imageWorkbench.logFilter', next);
  } catch (error) {
    // ignore storage failures
  }
  renderLogs();
}


async function openPathInExplorer(path, label) {
  if (!path) {
    pushLog(`${label}未设置，暂时打不开。`);
    return;
  }
  try {
      throw new Error(result.error || `打开${label}失败`);
    if (!result.ok) {
      throw new Error(result.error || `打开${label}失败`);
    }
    updateStatusBadge(`状态: ${result.message || `已打开${label}`}`);
  } catch (error) {
    pushLog(`打开${label}失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge(`状态: 打开${label}失败`);
  }
}

function hasProcessedPreview() {
  if (!state.source || !state.preview) {
    return false;
  }
  return state.preview.path !== state.source.path || state.preview.label !== '\u6e90\u56fe';
}

function getProcessingSummary() {
  const summary = [];
  if (refs.upscaleEnabled?.checked) {
    summary.push('\u8d85\u5206');
  }
  if (refs.mosaicEnabled?.checked) {
    summary.push(
      state.regions.length
        ? `\u6253\u7801 ${state.regions.length} \u533a`
        : '\u6253\u7801\uff08\u5f85\u6846\u9009\uff09',
    );
  }
  if (refs.wmEnabled?.checked) {
    summary.push('\u6c34\u5370');
  }
  return summary;
}

function hasAnyBatchStep() {
  return !!(
    refs.upscaleEnabled?.checked
    || refs.wmEnabled?.checked
    || (refs.mosaicEnabled?.checked && state.regions.length)
  );
}

function getCurrentPixivPreflight() {
  const pixiv = readPixivSettings();
  const issues = [];

  if (!state.source) {
    issues.push('\u8bf7\u5148\u9009\u62e9\u56fe\u7247');
  }
  if (!pixiv.enabled) {
    issues.push('\u5148\u5728\u53d1\u5e03\u9875\u542f\u7528 Pixiv \u81ea\u52a8\u4e0a\u4f20');
  }
  if (state.pixivCurrent.running) {
    issues.push('\u5f53\u524d\u56fe\u7247\u7684 Pixiv \u4efb\u52a1\u8fd8\u5728\u8fdb\u884c\u4e2d');
  }
  if (pixiv.enabled && pixiv.upload_mode === 'direct') {
    if (!pixiv.cookie.trim()) {
      issues.push('Pixiv \u76f4\u4f20\u6a21\u5f0f\u7f3a\u5c11 Cookie');
    }
    if (!pixiv.csrf_token.trim()) {
      issues.push('Pixiv \u76f4\u4f20\u6a21\u5f0f\u7f3a\u5c11 CSRF Token');
    }
  }

  return { pixiv, issues };
}

function getBatchPreflight(options = {}) {
  const retryFailedOnly = !!options.retryFailedOnly;
  const batch = readBatchSettings();
  const pixiv = readPixivSettings();
  const failedFiles = Array.isArray(state.batch.failedFiles) ? state.batch.failedFiles : [];
  const issues = [];
  const warnings = [];

  if (!batch.input_dir) {
    issues.push('\u8fd8\u6ca1\u9009\u6279\u91cf\u8f93\u5165\u76ee\u5f55');
  }
  if (!batch.output_dir) {
    issues.push('\u8fd8\u6ca1\u9009\u6279\u91cf\u8f93\u51fa\u76ee\u5f55');
  }
  if (!hasAnyBatchStep()) {
    issues.push('\u81f3\u5c11\u542f\u7528\u4e00\u4e2a\u5904\u7406\u6b65\u9aa4\uff1b\u6253\u7801\u8fd8\u9700\u8981\u5148\u6846\u9009\u533a\u57df');
  }
  if (pixiv.enabled && pixiv.upload_mode === 'direct') {
    if (!pixiv.cookie.trim()) {
      issues.push('Pixiv \u76f4\u4f20\u6a21\u5f0f\u7f3a\u5c11 Cookie');
    }
    if (!pixiv.csrf_token.trim()) {
      issues.push('Pixiv \u76f4\u4f20\u6a21\u5f0f\u7f3a\u5c11 CSRF Token');
    }
  }
  if (pixiv.enabled && pixiv.upload_mode !== 'direct' && !pixiv.auto_submit) {
    warnings.push('\u6279\u91cf\u6d4f\u89c8\u5668\u624b\u52a8\u786e\u8ba4\u76ee\u524d\u53ea\u652f\u6301\u5355\u56fe\uff0c\u591a\u56fe\u4f1a\u88ab\u540e\u7aef\u62e6\u4e0b');
  }
  if (retryFailedOnly && !failedFiles.length) {
    issues.push('\u5f53\u524d\u6ca1\u6709\u53ef\u91cd\u8dd1\u7684\u5931\u8d25\u9879');
  }

  return { batch, pixiv, failedFiles, issues, warnings };
}

function setButtonAvailability(button, enabled, reason = '') {
  if (!button) {
    return;
  }
  button.disabled = !enabled;
  button.title = enabled ? '' : reason;
}

function configureGuideButton(button, config) {
  if (!button) {
    return;
  }
  if (!config) {
    button.classList.add('hidden');
    button.dataset.action = '';
    button.textContent = '';
    button.disabled = true;
    button.title = '';
    return;
  }
  button.classList.remove('hidden');
  button.dataset.action = config.action || '';
  button.textContent = config.label || '';
  setButtonAvailability(button, config.enabled !== false, config.reason || '');
}

function renderGuideSteps(items) {
  if (!refs.quickGuideSteps) {
    return;
  }
  refs.quickGuideSteps.innerHTML = '';
  (items || []).forEach((item) => {
    const card = document.createElement('div');
    card.className = `guide-step${item.done ? ' is-done' : ''}`;

    const title = document.createElement('strong');
    title.textContent = item.title || '';
    card.appendChild(title);

    const detail = document.createElement('span');
    detail.textContent = item.detail || '';
    card.appendChild(detail);

    refs.quickGuideSteps.appendChild(card);
  });
}

async function onQuickGuideAction(event) {
  const action = String(event?.currentTarget?.dataset?.action || '').trim();
  if (!action) {
    return;
  }

  switch (action) {
    case 'open-image':
      await onOpenImage();
      break;
    case 'go-edit':
      setSidebarPage('edit');
      break;
    case 'go-publish':
      setSidebarPage('publish');
      break;
    case 'render-preview':
      await onRenderPreview();
      break;
    case 'export':
      await onExport();
      break;
    case 'current-pixiv':
      await onTestPixivUploadCurrent();
      break;
    case 'capture-pixiv-debug':
      await onCapturePixivDebug();
      break;
    case 'open-exported':
      await openPathInExplorer(state.ui.lastExportedPath, '\u5bfc\u51fa\u7ed3\u679c');
      break;
    default:
      break;
  }
}

function updateQuickStartGuide() {
  if (!refs.quickStartGuide) {
    return;
  }

  const sourceReady = !!state.source;
  const processedPreview = hasProcessedPreview();
  const processingSummary = getProcessingSummary();
  const pixivState = getCurrentPixivPreflight();
  const pixivReady = pixivState.issues.length === 0;
  let title = '';
  let lead = '';
  let hint = '';
  let steps = [];
  let primary = null;
  let secondary = null;

  refs.quickStartGuide.classList.remove('hidden');

  if (!sourceReady) {
    title = '\u5148\u9009\u4e00\u5f20\u56fe';
    lead = '\u4ece\u672c\u5730\u9009\u62e9\u4e00\u5f20\u56fe\uff0c\u6216\u76f4\u63a5\u62d6\u8fdb\u53f3\u4fa7\u5de5\u4f5c\u53f0\u3002';
    hint = '\u7b2c\u4e00\u6b21\u4e0d\u9700\u8981\u4e00\u53e3\u6c14\u5168\u90e8\u914d\u597d\uff0c\u5148\u8dd1\u901a\u4e00\u5f20\u56fe\u6700\u7a33\u3002';
    steps = [
      { title: '1. \u5148\u9009\u56fe', detail: '\u53f3\u4fa7\u5de5\u4f5c\u533a\u652f\u6301\u76f4\u63a5\u62d6\u5165\uff0c\u4e5f\u53ef\u4ee5\u4ece\u6700\u8fd1\u8bb0\u5f55\u6062\u590d\u3002', done: false },
      { title: '2. \u518d\u8c03\u53c2', detail: '\u53bb\u7f16\u8f91\u9875\u6253\u5f00\u6c34\u5370\u3001\u6253\u7801\u6216\u8d85\u5206\uff0c\u4e0d\u7528\u4e00\u6b21\u6027\u5168\u5f00\u3002', done: false },
      { title: '3. \u770b\u9884\u89c8\u518d\u51b3\u5b9a', detail: '\u5148\u770b\u4e00\u773c\u9884\u89c8\uff0c\u518d\u9009\u62e9\u5bfc\u51fa\u6216 Pixiv \u6d41\u7a0b\u3002', done: false },
    ];
    primary = { label: '\u9009\u62e9\u56fe\u7247', action: 'open-image' };
  } else if (state.pixivCurrent.running) {
    title = '\u5355\u56fe Pixiv \u4efb\u52a1\u8fdb\u884c\u4e2d';
    lead = state.pixivCurrent.status || '\u540e\u53f0\u6b63\u5728\u5904\u7406\u5f53\u524d\u56fe\u7247\u3002';
    hint = '\u65e5\u5fd7\u4f1a\u6301\u7eed\u66f4\u65b0\uff0c\u4e0d\u7528\u53cd\u590d\u70b9\u6309\u94ae\u50ac\u5b83\u3002';
    steps = [
      { title: '\u5f53\u524d\u56fe\u7247\u5df2\u9501\u5b9a', detail: state.source.fileName || '', done: true },
      { title: '\u540e\u53f0\u6b63\u5728\u6267\u884c', detail: state.pixivCurrent.status || '\u6b63\u5728\u5904\u7406\u4e2d', done: false },
      { title: '\u7b49\u5b83\u505c\u5728\u8349\u7a3f\u9875\u6216\u81ea\u52a8\u6295\u7a3f\u5b8c\u6210', detail: '\u5982\u679c\u662f\u624b\u52a8\u6a21\u5f0f\uff0c\u7b49\u6d4f\u89c8\u5668\u505c\u4e0b\u6765\u518d\u53bb\u68c0\u67e5\u5373\u53ef\u3002', done: false },
    ];
    secondary = { label: '\u53bb\u53d1\u5e03\u9875', action: 'go-publish' };
  } else if (state.pixivCurrent.failed) {
    title = '\u5355\u56fe Pixiv \u6d41\u7a0b\u6ca1\u8dd1\u901a';
    lead = state.pixivCurrent.status || '\u8fd9\u6b21 Pixiv \u4efb\u52a1\u6ca1\u6709\u5b8c\u6210\u3002';
    hint = '\u5148\u56de\u53d1\u5e03\u9875\u68c0\u67e5 Pixiv \u8bbe\u7f6e\uff0c\u4fee\u5b8c\u518d\u8bd5\u4f1a\u66f4\u7a33\u3002';
    steps = [
      { title: '\u5f53\u524d\u56fe\u7247\u8fd8\u5728', detail: state.source.fileName || '', done: true },
      { title: '\u672c\u6b21\u62a5\u9519', detail: state.pixivCurrent.status || '\u8bf7\u67e5\u770b\u65e5\u5fd7', done: false },
      { title: '\u4e0b\u4e00\u6b65', detail: '\u8c03\u6574 Pixiv \u8bbe\u7f6e\u540e\u518d\u91cd\u8bd5\u3002', done: false },
    ];
    primary = { label: '\u53bb\u53d1\u5e03\u9875', action: 'go-publish' };
    if (pixivState.pixiv.enabled) {
      secondary = { label: getQuickPixivActionLabel(), action: 'current-pixiv', enabled: pixivReady, reason: pixivState.issues[0] || '' };
    }
  } else if (state.pixivCurrent.draftReady) {
    title = 'Pixiv \u8349\u7a3f\u5df2\u5c31\u7eea';
    lead = '\u6d4f\u89c8\u5668\u5df2\u505c\u5728\u6295\u7a3f\u9875\uff0c\u73b0\u5728\u53ea\u9700\u68c0\u67e5\u540e\u624b\u52a8\u53d1\u5e03\u3002';
    hint = '\u8981\u662f\u60f3\u56de\u6536\u73b0\u573a\uff0c\u53ef\u4ee5\u987a\u624b\u6293\u4e00\u4efd Pixiv \u8c03\u8bd5\u5feb\u7167\u3002';
    steps = [
      { title: '\u5f53\u524d\u56fe\u7247\u5df2\u5904\u7406', detail: state.source.fileName || '', done: true },
      { title: 'Pixiv \u8349\u7a3f\u5df2\u6253\u5f00', detail: state.pixivCurrent.status || '\u6d4f\u89c8\u5668\u5df2\u5c31\u4f4d', done: true },
      { title: '\u6700\u540e\u68c0\u67e5', detail: '\u518d\u786e\u8ba4\u4e00\u904d\u6807\u9898\u3001\u6807\u7b7e\u548c\u6027\u63cf\u5199\uff0c\u65e0\u8bef\u540e\u518d\u70b9\u6295\u7a3f\u3002', done: false },
    ];
    primary = { label: '\u6293\u53d6 Pixiv \u5feb\u7167', action: 'capture-pixiv-debug' };
    secondary = { label: '\u53bb\u53d1\u5e03\u9875', action: 'go-publish' };
  } else if (state.ui.lastExportedPath) {
    title = '\u7ed3\u679c\u5df2\u5bfc\u51fa';
    lead = `\u521a\u624d\u7684\u7ed3\u679c\u5df2\u5199\u5230\uff1a${basename(state.ui.lastExportedPath)}`;
    hint = pixivReady
      ? '\u8fd8\u53ef\u4ee5\u76f4\u63a5\u7528\u5f53\u524d\u56fe\u7247\u7ee7\u7eed\u5355\u56fe Pixiv \u6d41\u7a0b\u3002'
      : '\u4f60\u53ef\u4ee5\u5148\u6253\u5f00\u5bfc\u51fa\u4f4d\u7f6e\u770b\u6210\u54c1\uff0c\u6216\u7ee7\u7eed\u8c03\u6574\u5f53\u524d\u56fe\u7247\u3002';
    steps = [
      { title: '\u5f53\u524d\u56fe\u7247', detail: state.source.fileName || '', done: true },
      { title: '\u5904\u7406\u7ed3\u679c\u5df2\u843d\u76d8', detail: basename(state.ui.lastExportedPath), done: true },
      { title: '\u4e0b\u4e00\u6b65', detail: pixivReady ? '\u53ef\u4ee5\u76f4\u63a5\u5355\u56fe Pixiv\uff0c\u6216\u8005\u6362\u4e0b\u4e00\u5f20\u56fe\u3002' : '\u53ef\u4ee5\u6253\u5f00\u5bfc\u51fa\u4f4d\u7f6e\u518d\u7ee7\u7eed\u8c03\u6574\u3002', done: false },
    ];
    primary = { label: '\u6253\u5f00\u5bfc\u51fa\u4f4d\u7f6e', action: 'open-exported' };
    secondary = pixivReady
      ? { label: getQuickPixivActionLabel(), action: 'current-pixiv' }
      : { label: '\u53bb\u7f16\u8f91\u9875', action: 'go-edit' };
  } else if (processedPreview) {
    title = pixivReady
      ? '\u9884\u89c8\u5df2\u5c31\u7eea\uff0c\u53ef\u4ee5\u5bfc\u51fa\u6216\u5355\u56fe Pixiv'
      : '\u9884\u89c8\u5df2\u5c31\u7eea';
    lead = processingSummary.length
      ? `\u8fd9\u5f20\u56fe\u5c06\u4ee5 ${processingSummary.join('\u3001')} \u7684\u7ec4\u5408\u8f93\u51fa\u3002`
      : '\u5f53\u524d\u5904\u7406\u7ed3\u679c\u5df2\u751f\u6210\uff0c\u73b0\u5728\u53ef\u4ee5\u5bfc\u51fa\u6210\u54c1\u3002';
    hint = pixivReady
      ? '\u5355\u56fe Pixiv \u53ea\u4f1a\u5904\u7406\u5f53\u524d\u8fd9\u5f20\u56fe\uff0c\u4e0d\u4f1a\u8bfb\u53d6\u6279\u91cf\u76ee\u5f55\u3002'
      : (pixivState.issues[0] || '\u53ef\u4ee5\u5148\u5bfc\u51fa\u7ed3\u679c\uff0c\u4e4b\u540e\u518d\u51b3\u5b9a\u662f\u5426\u6295\u7a3f\u3002');
    steps = [
      { title: '\u5df2\u8f7d\u5165\u5f53\u524d\u56fe', detail: state.source.fileName || '', done: true },
      { title: '\u9884\u89c8\u7ed3\u679c\u5df2\u51c6\u5907\u597d', detail: state.preview?.fileName || '', done: true },
      { title: '\u73b0\u5728\u53ef\u4ee5', detail: pixivReady ? '\u9009\u62e9\u5bfc\u51fa\uff0c\u6216\u8005\u76f4\u63a5\u7ee7\u7eed Pixiv \u6d41\u7a0b\u3002' : '\u5148\u5bfc\u51fa\u6210\u54c1\uff0c\u6216\u8005\u53bb\u53d1\u5e03\u9875\u8865\u9f50 Pixiv \u8bbe\u7f6e\u3002', done: false },
    ];
    primary = pixivReady
      ? { label: getQuickPixivActionLabel(), action: 'current-pixiv' }
      : { label: '\u5bfc\u51fa\u7ed3\u679c', action: 'export' };
    secondary = pixivReady
      ? { label: '\u5bfc\u51fa\u7ed3\u679c', action: 'export' }
      : { label: '\u53bb\u7f16\u8f91\u9875', action: 'go-edit' };
  } else {
    title = '\u4e0b\u4e00\u6b65\uff1a\u5148\u751f\u6210\u9884\u89c8';
    lead = processingSummary.length
      ? `\u5f53\u524d\u4f1a\u5904\u7406\uff1a${processingSummary.join('\u3001')}`
      : '\u4f60\u53ef\u4ee5\u5148\u76f4\u63a5\u751f\u6210\u4e00\u5f20\u9884\u89c8\uff0c\u6216\u8005\u5148\u53bb\u7f16\u8f91\u9875\u6253\u5f00\u9700\u8981\u7684\u5904\u7406\u6b65\u9aa4\u3002';
    hint = refs.mosaicEnabled?.checked && !state.regions.length
      ? '\u4f60\u5df2\u542f\u7528\u6253\u7801\uff0c\u4f46\u8fd8\u6ca1\u6709\u6846\u9009\u533a\u57df\uff0c\u8fd9\u4e00\u6b65\u76ee\u524d\u8fd8\u4e0d\u4f1a\u751f\u6548\u3002'
      : '\u5148\u770b\u9884\u89c8\u518d\u51b3\u5b9a\u662f\u76f4\u63a5\u5bfc\u51fa\uff0c\u8fd8\u662f\u7ee7\u7eed Pixiv \u6d41\u7a0b\u3002';
    steps = [
      { title: '\u5df2\u9009\u56fe', detail: state.source.fileName || '', done: true },
      { title: '\u8c03\u6574\u5904\u7406\u6b65\u9aa4', detail: processingSummary.length ? `\u5f53\u524d\u7ec4\u5408\uff1a${processingSummary.join('\u3001')}` : '\u8fd8\u6ca1\u6709\u6253\u5f00\u4efb\u4f55\u5904\u7406\u6b65\u9aa4\uff0c\u4e5f\u53ef\u4ee5\u76f4\u63a5\u9884\u89c8\u539f\u56fe\u3002', done: processingSummary.length > 0 },
      { title: '\u751f\u6210\u9884\u89c8', detail: '\u5148\u770b\u4e00\u773c\u6548\u679c\uff0c\u518d\u51b3\u5b9a\u5bfc\u51fa\u6216 Pixiv\u3002', done: false },
    ];
    primary = { label: '\u751f\u6210\u9884\u89c8', action: 'render-preview' };
    secondary = { label: '\u53bb\u7f16\u8f91\u9875', action: 'go-edit' };
  }

  refs.quickGuideTitle.textContent = title;
  refs.quickGuideLead.textContent = lead;
  refs.quickGuideHint.textContent = hint;
  renderGuideSteps(steps);
  configureGuideButton(refs.quickGuidePrimaryBtn, primary);
  configureGuideButton(refs.quickGuideSecondaryBtn, secondary);
}

function updateWorkspaceActionState() {
  const sourceReady = !!state.source;
  const processedPreview = hasProcessedPreview();
  const processingSummary = getProcessingSummary();
  const pixivState = getCurrentPixivPreflight();
  const pixivReason = pixivState.issues[0] || '';

  setButtonAvailability(
    refs.renderPreviewBtn,
    sourceReady,
    '\u8bf7\u5148\u9009\u62e9\u56fe\u7247',
  );
  setButtonAvailability(
    refs.exportBtn,
    sourceReady,
    '\u8bf7\u5148\u9009\u62e9\u56fe\u7247',
  );
  setButtonAvailability(
    refs.resetPreviewBtn,
    sourceReady && processedPreview,
    sourceReady ? '\u5f53\u524d\u5df2\u7ecf\u662f\u6e90\u56fe' : '\u8bf7\u5148\u9009\u62e9\u56fe\u7247',
  );
  setButtonAvailability(refs.quickPixivUploadBtn, pixivState.issues.length === 0, pixivReason);
  setButtonAvailability(refs.testPixivUploadBtn, pixivState.issues.length === 0, pixivReason);

  if (refs.quickActionHint) {
    const notes = [];
    if (!sourceReady) {
      notes.push('\u5148\u9009\u4e00\u5f20\u56fe\uff0c\u9884\u89c8\u3001\u5bfc\u51fa\u548c\u5355\u56fe Pixiv \u624d\u4f1a\u53ef\u7528\u3002');
    } else if (!processingSummary.length) {
      notes.push('\u5f53\u524d\u6ca1\u6709\u542f\u7528\u5904\u7406\u6b65\u9aa4\uff0c\u751f\u6210\u9884\u89c8\u548c\u5bfc\u51fa\u4f1a\u76f4\u63a5\u6cbf\u7528\u539f\u56fe\u3002');
    } else {
      notes.push(`\u5f53\u524d\u4f1a\u6267\u884c\uff1a${processingSummary.join('\u3001')}\u3002`);
    }
    if (sourceReady && pixivState.issues.length) {
      notes.push(pixivState.issues[0]);
    } else if (sourceReady && pixivState.pixiv.enabled) {
      notes.push('\u5355\u56fe Pixiv \u53ea\u4f1a\u5904\u7406\u5f53\u524d\u5de5\u4f5c\u533a\u8fd9\u5f20\u56fe\uff0c\u4e0d\u4f1a\u8bfb\u53d6\u6279\u91cf\u76ee\u5f55\u3002');
    }
    refs.quickActionHint.textContent = notes.join(' ');
  }
}

function renderBatchRecovery(snapshot = {}) {
  const safe = snapshot || {};
  const lastError = String(safe.lastError || '').trim();
  const failedFiles = Array.isArray(safe.failedFiles) ? safe.failedFiles : [];
  const hasRecovery = !!lastError || failedFiles.length > 0;

  if (refs.batchRecoveryCard) {
    refs.batchRecoveryCard.classList.toggle('hidden', !hasRecovery);
  }
  if (refs.batchLastError) {
    refs.batchLastError.textContent = lastError || '\u5f53\u524d\u8fd8\u6ca1\u6709\u6279\u91cf\u9519\u8bef\u3002';
  }
  if (refs.batchFailedFiles) {
    refs.batchFailedFiles.innerHTML = '';
    failedFiles.forEach((name) => {
      const item = document.createElement('span');
      item.className = 'failed-file-chip';
      item.textContent = String(name || '');
      refs.batchFailedFiles.appendChild(item);
    });
  }
  updateBatchRecovery();
}

function updateBatchRecovery() {
  const hasInput = !!refs.batchInputDir?.value.trim();
  const hasOutput = !!refs.batchOutputDir?.value.trim();
  if (refs.openBatchInputDirBtn) {
    refs.openBatchInputDirBtn.disabled = !hasInput;
  }
  if (refs.openBatchOutputDirBtn) {
    refs.openBatchOutputDirBtn.disabled = !hasOutput;
  }
  if (refs.viewBatchErrorsBtn) {
    refs.viewBatchErrorsBtn.disabled = refs.batchRecoveryCard?.classList.contains('hidden') ?? true;
  }
  updateBatchActionState();
}

function updateBatchActionState() {
  const readiness = getBatchPreflight();
  const retryReadiness = getBatchPreflight({ retryFailedOnly: true });
  const running = !!state.batch.running;
  const cancelRequested = !!state.batch.cancelRequested;
  const failedFiles = retryReadiness.failedFiles || [];

  if (refs.retryFailedBatchBtn) {
    refs.retryFailedBatchBtn.textContent = failedFiles.length
      ? `\u53ea\u91cd\u8dd1\u5931\u8d25\u9879\uff08${failedFiles.length}\uff09`
      : '\u53ea\u91cd\u8dd1\u5931\u8d25\u9879';
  }

  setButtonAvailability(
    refs.startBatchBtn,
    !running && readiness.issues.length === 0,
    running ? '\u5f53\u524d\u5df2\u6709\u6279\u91cf\u4efb\u52a1\u5728\u8fd0\u884c' : (readiness.issues[0] || ''),
  );
  setButtonAvailability(
    refs.stopBatchBtn,
    running && !cancelRequested,
    running
      ? '\u505c\u6b62\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u6b63\u5728\u7b49\u5f85\u5f53\u524d\u56fe\u7247\u5b8c\u6210'
      : '\u5f53\u524d\u6ca1\u6709\u8fd0\u884c\u4e2d\u7684\u6279\u91cf\u4efb\u52a1',
  );
  setButtonAvailability(
    refs.retryFailedBatchBtn,
    !running && retryReadiness.issues.length === 0,
    running ? '\u8bf7\u5148\u7b49\u5f53\u524d\u6279\u91cf\u4efb\u52a1\u7ed3\u675f' : (retryReadiness.issues[0] || ''),
  );

  if (refs.batchActionHint) {
    const batchLabel = readiness.batch.input_dir && readiness.batch.output_dir
      ? `${basename(readiness.batch.input_dir)} -> ${basename(readiness.batch.output_dir)}`
      : '';
    let message = '';
    if (running) {
      message = state.batch.status || (state.batch.retryMode ? '\u6b63\u5728\u91cd\u8dd1\u5931\u8d25\u9879' : '\u6279\u91cf\u4efb\u52a1\u8fd0\u884c\u4e2d');
    } else if (readiness.issues.length) {
      message = readiness.issues[0];
    } else if (failedFiles.length) {
      message = `\u4e0a\u4e00\u8f6e\u6709 ${failedFiles.length} \u5f20\u5931\u8d25\u56fe\uff0c\u53ef\u4ee5\u76f4\u63a5\u53ea\u91cd\u8dd1\u5931\u8d25\u9879\u3002`;
    } else if (readiness.warnings.length) {
      message = readiness.warnings[0];
    } else if (batchLabel) {
      message = `\u51c6\u5907\u597d\u540e\uff0c\u5c31\u4f1a\u4ece ${batchLabel} \u5f00\u59cb\u6574\u6279\u5904\u7406\u3002`;
    } else {
      message = '\u9009\u597d\u8f93\u5165\u548c\u8f93\u51fa\u76ee\u5f55\u540e\uff0c\u5c31\u53ef\u4ee5\u4ece\u8fd9\u91cc\u5f00\u59cb\u6574\u6279\u5904\u7406\u3002';
    }
    refs.batchActionHint.textContent = message;
  }
}

function refreshExperienceUi() {
  updateQuickStartGuide();
  updateWorkspaceActionState();
  updateBatchActionState();
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
  fillSelect(refs.pixivSexualDepiction, data.pixivSexualDepictionOptions || []);
  fillSelect(refs.pixivTagLanguage, data.pixivTagLanguageOptions || []);
  fillSelect(refs.pixivSafetyMode, data.pixivSafetyModeOptions || []);
  fillSelect(refs.pixivLlmTitleStyle, PIXIV_TITLE_STYLE_OPTIONS);
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
  applyPixivCurrentSnapshot(state.bootstrap?.pixivCurrent || {}, { pushLogs: false });
  updateBatchRecovery();
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

function resolvePixivTitleStylePrompt(style) {
  return PIXIV_TITLE_STYLE_PROMPTS[String(style || 'default')] ?? '';
}

function syncPixivTitlePromptPresetState() {
  const style = refs.pixivLlmTitleStyle?.value || 'default';
  const presetPrompt = resolvePixivTitleStylePrompt(style);
  const currentPrompt = refs.pixivLlmPromptTitle?.value || '';
  if (style !== 'custom' && currentPrompt !== presetPrompt) {
    refs.pixivLlmPromptTitle.value = presetPrompt;
  }
}

function syncPixivTitleStyleFromPrompt() {
  if (!refs.pixivLlmTitleStyle || !refs.pixivLlmPromptTitle) {
    return;
  }
  const currentPrompt = refs.pixivLlmPromptTitle.value || '';
  const matched = PIXIV_TITLE_STYLE_OPTIONS.find((item) => {
    if (item.value === 'custom') {
      return false;
    }
    return resolvePixivTitleStylePrompt(item.value) === currentPrompt;
  });
  ensureSelectValue(refs.pixivLlmTitleStyle, matched ? matched.value : 'custom');
}

function resetPixivTitlePromptToPreset() {
  syncPixivTitlePromptPresetState();
  syncPixivTitleStyleFromPrompt();
  scheduleSettingsSave();
  refreshExperienceUi();
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
    mixed: 'YourName 路 龙族助手 Watermark 预览 2026',
    zh: '龙族助手水印预览 路 你好世界',
    en: 'Dragon Watermark Preview 路 Sample 2026',
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
    preview = customPath ? `自定义：${basename(customPath)}` : '鑷畾涔夛細鏈€夋嫨瀛椾綋鏂囦欢';
  } else if (selected) {
    preview = getSelectedOptionLabel(refs.wmFontPreset) || `棰勮锛?{basename(selected)}`;
  }

  refs.wmFontPreview.textContent = `褰撳墠瀛椾綋锛?{preview}`;
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
      throw new Error(result.error || '瀛椾綋棰勮加载失败');
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
    option.textContent = `${item.family} 路 ${item.category || 'uncategorized'} 路 ${item.variant}`;
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
    refs.fontCatalogStatus.textContent = result.message || `宸茶鍙?${result.items?.length || 0} 娆?Google Fonts 字体`;
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
  refs.fontCatalogStatus.textContent = `姝ｅ湪涓嬭浇锛?{item.family}`;
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
  updateBatchRecovery();
}

function hydratePixivForm(pixiv) {
  state.ui.pixivSessionCookie = pixiv.cookie || '';
  state.ui.pixivSessionCsrfToken = pixiv.csrf_token || '';
  state.ui.pixivCanTestDirect = !!state.ui.pixivSessionCookie;
  refs.pixivEnabled.checked = !!pixiv.enabled;
  ensureSelectValue(refs.pixivUploadMode, pixiv.upload_mode || 'browser');
  ensureSelectValue(refs.pixivBrowser, pixiv.browser_channel || 'msedge');
  ensureSelectValue(refs.pixivVisibility, pixiv.visibility || 'public');
  ensureSelectValue(refs.pixivAge, pixiv.age_restriction || 'all');
  ensureSelectValue(refs.pixivSexualDepiction, pixiv.sexual_depiction || 'auto');
  ensureSelectValue(refs.pixivTagLanguage, pixiv.tag_language || 'ja_priority');
  ensureSelectValue(refs.pixivSafetyMode, pixiv.safety_mode || 'auto');
  refs.pixivSubmitMode.value = pixiv.auto_submit ? 'auto' : 'manual';
  refs.pixivProfileDir.value = pixiv.profile_dir || '';
  refs.pixivCookie.value = state.ui.pixivSessionCookie;
  refs.pixivCsrfToken.value = state.ui.pixivSessionCsrfToken;
  refs.pixivLlmEnabled.checked = !!pixiv.llm_enabled;
  refs.pixivLlmImageEnabled.checked = !!pixiv.llm_image_enabled;
  refs.pixivLlmTitleEnabled.checked = !!pixiv.llm_title_enabled;
  ensureSelectValue(refs.pixivLlmTitleStyle, pixiv.llm_title_style || 'default');
  refs.pixivLlmBaseUrl.value = pixiv.llm_base_url || 'https://api.openai.com/v1';
  refs.pixivLlmApiKey.value = pixiv.llm_api_key || '';
  refs.pixivRememberLlmApiKey.checked = !!pixiv.remember_llm_api_key;
  renderPixivLlmModelOptions([]);
  applyPixivLlmModelSelection(pixiv.llm_model || '');
  refs.pixivLlmTemperature.value = String(pixiv.llm_temperature ?? 0.1);
  refs.pixivLlmTimeout.value = String(pixiv.llm_timeout ?? 60);
  refs.pixivLlmPromptMetadata.value = pixiv.llm_metadata_prompt || '';
  refs.pixivLlmPromptImage.value = pixiv.llm_image_prompt || '';
  refs.pixivLlmPromptTitle.value = pixiv.llm_title_prompt || '';
  syncPixivTitleStyleFromPrompt();
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
    empty.innerHTML = '<strong>杩樻病鏈夋渶杩戣褰</strong><span>閫変竴娆″浘鐗囧悗锛岃繖閲屼細淇濈暀鏈€杩?8 寮狅紝鏂逛究蹇€熷洖鍒板伐浣滅幇鍦恒€</span>';
    refs.recentList.appendChild(empty);
    return;
  }

  state.recentImages.forEach((item, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'recent-item';
    button.innerHTML = `<strong>${escapeHtml(item.fileName)}</strong><span>#${index + 1} 路 ${escapeHtml(item.parent)}</span>`;
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
  updateStatusBadge('鐘舵€? 正在加载图片');
  const result = await window.pywebview.api.open_image_path(path);
  handleLoadResult(result, sourceLabel);
}

async function loadImageFile(file, sourceLabel = '拖拽载入') {
  if (!file) {
    pushLog('娌℃湁鍙取的拖拽文件');
    updateStatusBadge('鐘舵€? 拖拽载入失败');
    return;
  }

  const filePath = String(file.path || '').trim();
  if (filePath) {
    await loadImagePath(filePath, sourceLabel);
    return;
  }

  updateStatusBadge('鐘舵€? 正在读取拖拽图片');
  try {
    const dataUrl = await fileToDataUrl(file);
    const result = await window.pywebview.api.open_image_blob(file.name || 'dropped-image', dataUrl);
    handleLoadResult(result, `${sourceLabel}（兼容模式）`);
  } catch (error) {
    pushLog(`拖拽载入失败: ${error?.message || error}`);
    updateStatusBadge('鐘舵€? 拖拽载入失败');
  }
}

function handleLoadResult(result, sourceLabel) {
  if (!result.ok) {
    if (!result.cancelled) {
      pushLog(result.error || '加载图片失败');
      updateStatusBadge('鐘舵€? 载入失败');
    }
    return;
  }

  state.regions = [];
  renderRegionChips();
  updateSource(result.source);
  updatePreview(result.preview || result.source);
  updateRecentImages(result.recentImages || state.recentImages);
  updateStatusBadge(`鐘舵€? ${result.message}`);
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
    pushLog(`${label}: ${result.path}`);
    updateBatchRecovery();
    refreshExperienceUi();
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
    updateStatusBadge('鐘舵€? 读取模型列表失败');
  } finally {
    syncPixivFieldState();
  }
}

async function onPreviewPixivSubmission() {
  refs.previewPixivBtn.disabled = true;
  updateStatusBadge('鐘舵€? 正在生成当前 Pixiv 鎶曠棰勮');
  const result = await window.pywebview.api.preview_pixiv_submission(buildSettings());
  if (!result.ok) {
    pushLog(result.error || 'Pixiv 鎶曠棰勮生成失败');
    updateStatusBadge('鐘舵€? Pixiv 鎶曠棰勮生成失败');
    refs.previewPixivBtn.disabled = false;
    syncPixivFieldState();
    return;
  }

  const preview = result.preview || {};
  pushLog(`[Pixiv Preview] File: ${preview.fileName || ''}`);
  pushLog(`[Pixiv Preview] Title: ${preview.title || ''}`);
  if (preview.titleAiEnabled || preview.titleStyleLabel) {
    pushLog(`[Pixiv Preview] Title style: ${preview.titleStyleLabel || preview.titleStyle || ''}${preview.titleAiEnabled ? ' / AI润色已开启' : ''}`);
  }
  pushLog(`[Pixiv Preview] Tags (${preview.tagCount || 0}/${preview.maxTags || 10}): ${((preview.tags || []).join(', ')) || '(empty)'}`);
  pushLog(`[Pixiv Preview] Caption: ${preview.caption || '(empty)'}`);
  pushLog(`[Pixiv Preview] Mode: ${preview.uploadModeLabel || preview.uploadMode || ''} / ${preview.submitModeLabel || preview.submitMode || ''}`);
  pushLog(`[Pixiv Preview] Visibility: ${preview.visibilityLabel || preview.visibility || ''} / ${preview.ageRestrictionLabel || preview.ageRestriction || ''}`);
  pushLog(`[Pixiv Preview] Sexual depiction: ${preview.sexualDepictionResolvedLabel || ''} (mode: ${preview.sexualDepictionModeLabel || ''}, source: ${preview.sexualDepictionSource || ''}${preview.sexualDepictionConfidence ? `, confidence: ${preview.sexualDepictionConfidence}` : ''}${preview.sexualDepictionReason ? `, reason: ${preview.sexualDepictionReason}` : ''})`);
  pushLog(`[Pixiv Preview] Upload file: ${preview.uploadFileName || ''} (${preview.uploadFormat || ''})`);
  (preview.infos || []).forEach((message) => pushLog(`[Pixiv Preview] ${message}`));
  (preview.warnings || []).forEach((message) => pushLog(`[Pixiv Preview] Warning: ${message}`));
  (preview.errors || []).forEach((message) => pushLog(`[Pixiv Preview] Error: ${message}`));
  updateStatusBadge('状态: ' + (result.message || 'Pixiv 投稿预览已就绪'));
  refs.previewPixivBtn.disabled = false;
  syncPixivFieldState();
}

async function onTestPixivUploadCurrent() {
  const actionLabel = getPixivCurrentActionLabel();
  updateStatusBadge(`鐘舵€? 正在准备${actionLabel}`);
  try {
    const result = await window.pywebview.api.start_pixiv_upload_current(buildSettings());
    if (!result.ok) {
      (result.logs || []).forEach((message) => pushLog(message));
      pushLog(result.error || `Pixiv ${actionLabel}失败`);
      updateStatusBadge(`鐘舵€? Pixiv ${actionLabel}失败`);
      syncPixivFieldState();
      return;
    }
    applyPixivCurrentSnapshot(result);
  } catch (error) {
    pushLog(`Pixiv ${actionLabel}失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge(`鐘舵€? Pixiv ${actionLabel}失败`);
  }
}

function getFirstPixivTagHint() {
  return String(refs.pixivTags?.value || '')
    .split(/[\r\n,]+/)
    .map((item) => item.trim())
    .find(Boolean) || '';
}

async function onCapturePixivDebug() {
  refs.capturePixivDebugBtn.disabled = true;
  updateStatusBadge('鐘舵€? 正在抓取 Pixiv 调试快照');
  try {
    const result = await window.pywebview.api.capture_interactive_pixiv_debug(getFirstPixivTagHint());
    if (!result.ok) {
      (result.logs || []).forEach((message) => pushLog(message));
      pushLog(result.error || 'Pixiv 调试快照抓取失败');
      updateStatusBadge('鐘舵€? Pixiv 调试快照抓取失败');
      return;
    }

    (result.logs || []).forEach((message) => pushLog(message));
    updateStatusBadge(`鐘舵€? ${result.message || '宸叉姄鍙?Pixiv 调试快照'}`);
  } catch (error) {
    pushLog(`Pixiv 调试快照抓取失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('鐘舵€? Pixiv 调试快照抓取失败');
  } finally {
    syncPixivFieldState();
  }
}

async function onImportPixivBrowserAuth() {
  refs.importPixivAuthBtn.disabled = true;
  updatePixivDirectStatus('正在从浏览器导入 Pixiv 登录态…', 'pending');
  updateStatusBadge('状态: 正在导入 Pixiv 直传登录态');
  try {
    const result = await window.pywebview.api.import_pixiv_browser_auth({ pixiv: readPixivSettings() });
    if (!result.ok) {
      throw new Error(result.error || '导入 Pixiv 登录态失败');
    }

    ensureSelectValue(refs.pixivUploadMode, 'direct');
    if (result.browserChannel) {
      ensureSelectValue(refs.pixivBrowser, result.browserChannel);
    }
    state.ui.pixivSessionCookie = result.cookie || '';
    state.ui.pixivSessionCsrfToken = result.csrfToken || '';
    state.ui.pixivCanTestDirect = !!state.ui.pixivSessionCookie;
    refs.pixivCookie.value = state.ui.pixivSessionCookie;
    refs.pixivCsrfToken.value = state.ui.pixivSessionCsrfToken;
    (result.logs || []).forEach((message) => pushLog(message));
    if (state.bootstrap && result.config) {
      state.bootstrap.config = result.config;
    }
    await persistSettingsSilently();
    syncPixivFieldState();
    if (refs.testPixivDirectBtn && refs.pixivEnabled.checked && state.ui.pixivSessionCookie) {
      refs.testPixivDirectBtn.disabled = false;
    }
    let finalMessage = `${result.message}${result.cookieCount ? `（${result.cookieCount} 个 Cookie）` : ''}`;
    let authStatus = result.needsCsrfProbe ? 'pending' : 'saved';

    if (result.needsCsrfProbe && state.ui.pixivSessionCookie) {
      updatePixivDirectStatus('已导入 Cookie，正在自动检测直传并补齐 CSRF Token…', 'pending');
      updateStatusBadge('状态: 正在自动补齐 Pixiv CSRF Token');
      try {
        const probeResult = await window.pywebview.api.test_pixiv_direct({ pixiv: readPixivSettings() });
        if (!probeResult.ok) {
          throw new Error(probeResult.error || 'Pixiv 直传检测失败');
        }
        if (probeResult.csrfToken) {
          state.ui.pixivSessionCsrfToken = probeResult.csrfToken;
          refs.pixivCsrfToken.value = state.ui.pixivSessionCsrfToken;
        }
        (probeResult.logs || []).forEach((message) => pushLog(message));
        if (probeResult.url) {
          pushLog(`[Pixiv] 直传检测页面: ${probeResult.url}`);
        }
        if (state.bootstrap && probeResult.config) {
          state.bootstrap.config = probeResult.config;
        }
        await persistSettingsSilently();
        syncPixivFieldState();
        if (refs.testPixivDirectBtn) {
          refs.testPixivDirectBtn.disabled = false;
          refs.testPixivDirectBtn.classList.add('accent');
          refs.testPixivDirectBtn.classList.remove('ghost');
        }
        authStatus = probeResult.csrfToken ? 'saved' : 'pending';
        finalMessage = probeResult.message || finalMessage;
      } catch (probeError) {
        pushLog(`Pixiv 自动补齐 CSRF 失败: ${probeError && probeError.message ? probeError.message : probeError}`);
        authStatus = 'pending';
      }
    }

    updatePixivDirectStatus(
      finalMessage,
      authStatus,
    );
    updateStatusBadge(`状态: ${finalMessage}`);
  } catch (error) {
    syncPixivFieldState();
    updatePixivDirectStatus(
      `导入失败：${error && error.message ? error.message : error}`,
      'error',
    );
    pushLog(`导入 Pixiv 登录态失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: 导入 Pixiv 登录态失败');
  }
}

async function onTestPixivDirect() {
  refs.testPixivDirectBtn.disabled = true;
  updatePixivDirectStatus('正在检测 Pixiv 直传可用性…', 'pending');
  updateStatusBadge('状态: 正在检测 Pixiv 直传');
  try {
    const result = await window.pywebview.api.test_pixiv_direct({ pixiv: readPixivSettings() });
    if (!result.ok) {
      throw new Error(result.error || 'Pixiv 直传检测失败');
    }

    if (result.csrfToken) {
      state.ui.pixivSessionCsrfToken = result.csrfToken;
      refs.pixivCsrfToken.value = state.ui.pixivSessionCsrfToken;
    }
    if (refs.pixivCookie.value.trim() || state.ui.pixivSessionCookie) {
      state.ui.pixivCanTestDirect = true;
    }
    (result.logs || []).forEach((message) => pushLog(message));
    if (result.url) {
      pushLog(`[Pixiv] 直传检测页面: ${result.url}`);
    }
    if (state.bootstrap && result.config) {
      state.bootstrap.config = result.config;
    }
    await persistSettingsSilently();
    syncPixivFieldState();
    if (refs.testPixivDirectBtn && refs.pixivEnabled.checked && (refs.pixivCookie.value.trim() || state.ui.pixivSessionCookie)) {
      refs.testPixivDirectBtn.disabled = false;
    }
    const authStatus = result.needsCsrfProbe ? 'pending' : 'saved';
    updatePixivDirectStatus(result.message, authStatus);
    updateStatusBadge(`状态: ${result.message}`);
  } catch (error) {
    syncPixivFieldState();
    updatePixivDirectStatus(
      `检测失败：${error && error.message ? error.message : error}`,
      'error',
    );
    pushLog(`Pixiv 直传检测失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: Pixiv 直传检测失败');
  }
}
async function onTestPixivLlm() {
  refs.testPixivLlmBtn.disabled = true;
  updateStatusBadge('鐘舵€? 正在测试 Pixiv LLM');
  const result = await window.pywebview.api.test_pixiv_llm({ pixiv: readPixivSettings() });
  if (!result.ok) {
    pushLog(result.error || 'Pixiv LLM 测试失败');
    updateStatusBadge('鐘舵€? Pixiv LLM 测试失败');
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
  updateStatusBadge(`鐘舵€? ${result.message}`);
  syncPixivFieldState();
}

async function onStartBatch(options = {}) {
  const retryFailedOnly = !!options.retryFailedOnly;
  const readiness = getBatchPreflight({ retryFailedOnly });
  const failedFiles = Array.isArray(state.batch.failedFiles) ? state.batch.failedFiles.slice() : [];
  setSidebarPage('publish');

  if (readiness.issues.length) {
    const message = retryFailedOnly
      ? `\u6682\u65f6\u4e0d\u80fd\u91cd\u8dd1\u5931\u8d25\u9879\uff1a${readiness.issues[0]}`
      : readiness.issues[0];
    pushLog(message);
    updateStatusBadge(`\u72b6\u6001: ${message}`);
    refreshExperienceUi();
    return;
  }

  const payload = buildSettings();
  if (retryFailedOnly) {
    payload.batch.retry_failed_files = failedFiles;
  }

  refs.startBatchBtn.disabled = true;
  refs.stopBatchBtn.disabled = true;
  if (refs.retryFailedBatchBtn) {
    refs.retryFailedBatchBtn.disabled = true;
  }
  updateStatusBadge(`\u72b6\u6001: ${retryFailedOnly ? '\u6b63\u5728\u63d0\u4ea4\u5931\u8d25\u9879\u91cd\u8dd1' : '\u6b63\u5728\u63d0\u4ea4\u6279\u91cf\u4efb\u52a1'}`);
  refs.batchStatusText.textContent = retryFailedOnly ? '\u6b63\u5728\u63d0\u4ea4\u5931\u8d25\u9879\u91cd\u8dd1' : '\u6b63\u5728\u63d0\u4ea4\u6279\u91cf\u4efb\u52a1';
  refs.batchCurrentFile.textContent = retryFailedOnly
    ? `\u51c6\u5907\u91cd\u8dd1 ${failedFiles.length} \u4e2a\u5931\u8d25\u9879`
    : '\u7b49\u5f85\u540e\u53f0\u5f00\u59cb\u5904\u7406';
  refs.batchProgressFill.style.width = '0%';

  pushLog(
    retryFailedOnly
      ? `\u51c6\u5907\u91cd\u8dd1\u5931\u8d25\u9879\uff1a${failedFiles.join(', ')}`
      : `\u6279\u91cf\u4efb\u52a1\u51c6\u5907\u63d0\u4ea4\uff1a${readiness.batch.input_dir} -> ${readiness.batch.output_dir}`,
  );

  try {
    const result = await window.pywebview.api.start_batch(payload);
    if (!result.ok) {
      pushLog(result.error || (retryFailedOnly ? '\u5931\u8d25\u9879\u91cd\u8dd1\u4efb\u52a1\u521b\u5efa\u5931\u8d25' : '\u6279\u91cf\u4efb\u52a1\u521b\u5efa\u5931\u8d25'));
      updateStatusBadge(`\u72b6\u6001: ${retryFailedOnly ? '\u5931\u8d25\u9879\u91cd\u8dd1\u4efb\u52a1\u521b\u5efa\u5931\u8d25' : '\u6279\u91cf\u4efb\u52a1\u521b\u5efa\u5931\u8d25'}`);
      refs.batchStatusText.textContent = '\u521b\u5efa\u5931\u8d25';
      refreshExperienceUi();
      return;
    }

    applyBatchSnapshot(result);
  } catch (error) {
    pushLog(`\u6279\u91cf\u4efb\u52a1\u63d0\u4ea4\u5931\u8d25: ${error && error.message ? error.message : error}`);
    updateStatusBadge('\u72b6\u6001: \u6279\u91cf\u4efb\u52a1\u63d0\u4ea4\u5931\u8d25');
    refs.batchStatusText.textContent = '\u63d0\u4ea4\u5931\u8d25';
    refreshExperienceUi();
  }
}

async function onRetryFailedBatch() {
  await onStartBatch({ retryFailedOnly: true });
}

async function onStopBatch() {
  if (!state.batch.jobId || !window.pywebview?.api) {
    return;
  }
  refs.stopBatchBtn.disabled = true;
  updateStatusBadge('鐘舵€? 姝ｅ湪璇锋眰鍋滄批量任务');
  try {
    const result = await window.pywebview.api.stop_batch();
    if (!result.ok) {
      throw new Error(result.error || '鍋滄批量任务失败');
    }
    applyBatchSnapshot(result);
    pushLog(result.message || '已请求停止批量任务');
  } catch (error) {
    refs.stopBatchBtn.disabled = false;
    pushLog(`鍋滄批量任务失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('鐘舵€? 鍋滄批量任务失败');
  }
}

async function onRenderPreview() {
  if (!state.source) {
    pushLog('请先选择图片');
    return;
  }

  updateStatusBadge('鐘舵€? 正在生成预览');
  const result = await window.pywebview.api.render_preview(buildSettings());
  if (!result.ok) {
    pushLog(result.error || '预览失败');
    updateStatusBadge('鐘舵€? 预览失败');
    return;
  }

  updateSource(result.source);
  updatePreview(result.preview);
  (result.logs || []).forEach(pushLog);
  updateStatusBadge(`鐘舵€? ${result.message}`);
}

async function onExport() {
  if (!state.source) {
    pushLog('\u8bf7\u5148\u9009\u62e9\u56fe\u7247');
    return;
  }

  updateStatusBadge('\u72b6\u6001: \u6b63\u5728\u5bfc\u51fa');
  const result = await window.pywebview.api.export_result(buildSettings());
  if (!result.ok) {
    if (!result.cancelled) {
      pushLog(result.error || '\u5bfc\u51fa\u5931\u8d25');
      updateStatusBadge('\u72b6\u6001: \u5bfc\u51fa\u5931\u8d25');
    }
    return;
  }

  state.ui.lastExportedPath = result.exportedPath || '';
  if (result.preview) {
    updatePreview(result.preview);
  } else {
    refreshExperienceUi();
  }
  (result.logs || []).forEach(pushLog);
  updateStatusBadge(`\u72b6\u6001: ${result.message}`);
}

async function onResetPreview() {
  const result = await window.pywebview.api.reset_preview();
  if (!result.ok) {
    pushLog(result.error || '\u6062\u590d\u5931\u8d25');
    return;
  }
  state.ui.lastExportedPath = '';
  updatePreview(result.preview);
  updateStatusBadge(`\u72b6\u6001: ${result.message}`);
  pushLog(result.message);
}

function readBatchSettings() {
  return {
    input_dir: refs.batchInputDir.value.trim(),
    output_dir: refs.batchOutputDir.value.trim(),
  };
}

function readPixivSettings() {
  const cookie = refs.pixivCookie.value.trim() || state.ui.pixivSessionCookie || '';
  const csrfToken = refs.pixivCsrfToken.value.trim() || state.ui.pixivSessionCsrfToken || '';
  return {
    enabled: refs.pixivEnabled.checked,
    upload_mode: refs.pixivUploadMode.value,
    browser_channel: refs.pixivBrowser.value,
    visibility: refs.pixivVisibility.value,
    age_restriction: refs.pixivAge.value,
    sexual_depiction: refs.pixivSexualDepiction.value,
    auto_submit: refs.pixivSubmitMode.value === 'auto',
    tag_language: refs.pixivTagLanguage.value,
    safety_mode: refs.pixivSafetyMode.value,
    profile_dir: refs.pixivProfileDir.value.trim(),
    cookie,
    csrf_token: csrfToken,
    llm_enabled: refs.pixivLlmEnabled.checked,
    llm_image_enabled: refs.pixivLlmImageEnabled.checked,
    llm_title_enabled: refs.pixivLlmTitleEnabled.checked,
    llm_title_style: refs.pixivLlmTitleStyle.value,
    llm_base_url: refs.pixivLlmBaseUrl.value.trim(),
    llm_api_key: refs.pixivLlmApiKey.value.trim(),
    remember_llm_api_key: refs.pixivRememberLlmApiKey.checked,
    llm_model: getActivePixivLlmModelValue(),
    llm_temperature: Number.parseFloat(refs.pixivLlmTemperature.value || '0.1'),
    llm_timeout: Number.parseInt(refs.pixivLlmTimeout.value || '60', 10),
    llm_metadata_prompt: refs.pixivLlmPromptMetadata.value,
    llm_image_prompt: refs.pixivLlmPromptImage.value,
    llm_title_prompt: refs.pixivLlmPromptTitle.value,
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

function getPixivCurrentActionLabel() {
  const directMode = refs.pixivUploadMode.value === 'direct';
  const autoSubmit = refs.pixivSubmitMode.value === 'auto';
  return (directMode || autoSubmit)
    ? '处理并投稿当前图片'
    : '处理并打开当前图片 Pixiv 草稿';
}

function getQuickPixivActionLabel() {
  const directMode = refs.pixivUploadMode.value === 'direct';
  const autoSubmit = refs.pixivSubmitMode.value === 'auto';
  return (directMode || autoSubmit)
    ? '单图一键投稿'
    : '单图一键草稿';
}

function updatePixivModeHint() {
  const enabled = refs.pixivEnabled.checked;
  const directMode = refs.pixivUploadMode.value === 'direct';
  const manualSubmit = refs.pixivSubmitMode.value !== 'auto';
  const llmEnabled = refs.pixivLlmEnabled.checked;
  const llmImageEnabled = refs.pixivLlmImageEnabled.checked;
  const sexualMode = refs.pixivSexualDepiction.value || 'auto';
  refs.testPixivUploadBtn.textContent = getPixivCurrentActionLabel();
  if (refs.quickPixivUploadBtn) {
    refs.quickPixivUploadBtn.textContent = getQuickPixivActionLabel();
  }
  if (!enabled) {
    refs.pixivModeHint.textContent = '启用后，首页和发布页的当前图片按钮都会只处理当前加载或拖入的这张图；如果改用直传模式，还需要补齐 Cookie 和 CSRF Token。';
    return;
  }

  let message = '首页和发布页里的当前图片按钮，只会处理当前工作区中这张已加载或拖入的图片，不会读取批量目录。';
  message += directMode
    ? ' 当前会走 Cookie + CSRF 直传模式，处理完成后会直接尝试提交到 Pixiv。'
    : ' 当前会先打开浏览器草稿页，方便你在 Pixiv 投稿页里再检查一次标题、标签和说明。';

  if (!directMode && manualSubmit) {
    message += ' 如果要跑批量目录，浏览器手动确认目前只支持单图；多图请改用自动投稿。';
  }

  if (sexualMode === 'auto') {
    message += llmEnabled
      ? ' 性描写选项目前交给 LLM 自动判断，会结合当前图片内容来决定。'
      : ' 性描写选项当前仍是自动，但你还没启用 LLM，建议改成手动指定更稳。';
  } else if (sexualMode === 'yes') {
    message += ' 性描写选项会固定为有。';
  } else if (sexualMode === 'no') {
    message += ' 性描写选项会固定为无。';
  }

  if (llmEnabled && llmImageEnabled) {
    message += ' 标签整理会同时参考 metadata 和看图结果，再经 OpenAI-compatible 模型收敛成更贴近 Pixiv 的标签。';
  } else if (llmEnabled) {
    message += ' 标签整理当前只会基于 metadata，并交给 OpenAI-compatible 模型改写成更贴近 Pixiv 的表达。';
  }
  if (llmEnabled && refs.pixivLlmTitleEnabled.checked) {
    message += ' 标题会先按模板生成，再交给 LLM 做一次润色。';
  }

  if (refs.pixivSafetyMode.value === 'strict') {
    message += ' 严格安全模式下，疑似 NSFW 的图会先被拦下，不会自动投稿。';
  } else if (refs.pixivSafetyMode.value === 'auto') {
    message += ' 自动安全模式下，会结合内容与标签判断是否需要切到全年龄之外的 R-18 / R-18G 设置。';
  }

  refs.pixivModeHint.textContent = message;
}
function syncPixivFieldState() {
  const enabled = refs.pixivEnabled.checked;
  const directMode = refs.pixivUploadMode.value === 'direct';
  const llmEnabled = refs.pixivLlmEnabled.checked;
  const llmTitleEnabled = refs.pixivLlmTitleEnabled.checked;
  const pixivCurrentRunning = !!state.pixivCurrent.running;
  const pixivDraftReady = !!state.pixivCurrent.draftReady;
  const credentialSupported = state.bootstrap?.supportsCredentialStorage !== false;
  const effectiveCookie = refs.pixivCookie.value.trim() || state.ui.pixivSessionCookie || '';
  const effectiveCsrfToken = refs.pixivCsrfToken.value.trim() || state.ui.pixivSessionCsrfToken || '';
  const canTestDirectBySession = !!effectiveCookie || !!state.ui.pixivCanTestDirect;
  [
    refs.pixivUploadMode,
    refs.pixivVisibility,
    refs.pixivAge,
    refs.pixivSexualDepiction,
    refs.pixivSubmitMode,
    refs.pixivTagLanguage,
    refs.pixivSafetyMode,
    refs.pixivLlmEnabled,
    refs.pixivProfileDir,
    refs.browsePixivProfileBtn,
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
  ].forEach((control) => {
    control.disabled = !enabled;
  });

  refs.pixivBrowser.disabled = !enabled || directMode;
  refs.pixivProfileDir.disabled = !enabled || directMode;
  refs.browsePixivProfileBtn.disabled = !enabled || directMode;
  refs.pixivCookie.disabled = !enabled || !directMode;
  refs.pixivCsrfToken.disabled = !enabled || !directMode;
  refs.pixivLlmImageEnabled.disabled = !enabled || !llmEnabled;
  refs.pixivLlmTitleEnabled.disabled = !enabled || !llmEnabled;
  refs.pixivLlmTitleStyle.disabled = !enabled || !llmEnabled || !llmTitleEnabled;
  refs.resetPixivTitlePromptBtn.disabled = !enabled || !llmEnabled || !llmTitleEnabled;
  refs.pixivLlmBaseUrl.disabled = !enabled || !llmEnabled;
  refs.pixivLlmApiKey.disabled = !enabled || !llmEnabled;
  refs.pixivRememberLlmApiKey.disabled = !enabled || !llmEnabled || !credentialSupported;
  refs.pixivRememberLlmApiKey.title = credentialSupported ? '' : 'Windows Credential Manager is not available in this environment';
  refs.loadPixivLlmModelsBtn.disabled = !enabled || !llmEnabled;
  refs.pixivLlmModelPreset.disabled = !enabled || !llmEnabled;
  syncPixivLlmModelState();
  refs.pixivLlmTemperature.disabled = !enabled || !llmEnabled;
  refs.pixivLlmTimeout.disabled = !enabled || !llmEnabled;
  refs.pixivLlmPromptMetadata.disabled = !enabled || !llmEnabled;
  refs.pixivLlmPromptImage.disabled = !enabled || !llmEnabled;
  refs.pixivLlmPromptTitle.disabled = !enabled || !llmEnabled || !llmTitleEnabled;
  refs.testPixivLlmBtn.disabled = !enabled || !llmEnabled;
  refs.previewPixivBtn.disabled = !enabled || pixivCurrentRunning;
  refs.testPixivUploadBtn.disabled = !enabled || pixivCurrentRunning;
  if (refs.quickPixivUploadBtn) {
    refs.quickPixivUploadBtn.disabled = !enabled || pixivCurrentRunning;
  }
  if (refs.importPixivAuthBtn) {
    refs.importPixivAuthBtn.disabled = pixivCurrentRunning;
  }
  if (refs.testPixivDirectBtn) {
    const canTestDirect = !pixivCurrentRunning && canTestDirectBySession;
    refs.testPixivDirectBtn.disabled = !canTestDirect;
    refs.testPixivDirectBtn.classList.toggle('accent', canTestDirect);
    refs.testPixivDirectBtn.classList.toggle('ghost', !canTestDirect);
    refs.testPixivDirectBtn.title = canTestDirect
      ? '当前已经拿到 Pixiv Cookie，可以点这里自动补齐 CSRF Token'
      : '需要先拿到 Pixiv Cookie，才能检测直传';
  }
  refs.capturePixivDebugBtn.disabled = !enabled || directMode || pixivCurrentRunning || !pixivDraftReady;

  if (!effectiveCookie) {
    updatePixivDirectStatus('还没有 Pixiv 登录态；可以直接点从浏览器导入自动补齐 Cookie 和 CSRF。', 'idle');
  } else if (!effectiveCsrfToken) {
    updatePixivDirectStatus('Cookie 已填入，但还缺 CSRF Token；可以点检测直传自动补齐。', 'pending');
  } else if (!enabled) {
    updatePixivDirectStatus('直传凭证已经就绪；即使还没启用 Pixiv 自动上传，也可以先点检测直传确认可用性。', 'saved');
  } else if (directMode) {
    updatePixivDirectStatus('直传模式已准备好；建议正式投稿前先点一次检测直传。', 'saved');
  } else {
    updatePixivDirectStatus('直传凭证已经就绪；如果想无浏览器投稿，把上传方式切到 Cookie + CSRF 直传 就行。', 'saved');
  }

  updatePixivModeHint();
}

function updateBatchButton(running, cancelRequested = false) {
  refs.startBatchBtn.textContent = running ? '\u6279\u91cf\u5904\u7406\u4e2d...' : '\u5f00\u59cb\u6279\u91cf\u5904\u7406';
  refs.stopBatchBtn.textContent = cancelRequested ? '\u505c\u6b62\u4e2d...' : '\u505c\u6b62\u5904\u7406';
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

  refs.batchStatusText.textContent = safe.status || '\u672a\u5f00\u59cb';
  refs.batchProgressLabel.textContent = `${processed} / ${total}`;
  refs.batchProgressFill.style.width = `${percent}%`;
  refs.batchCurrentFile.textContent = safe.currentFile || (running ? (cancelRequested ? '\u505c\u6b62\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u7b49\u5f85\u5f53\u524d\u56fe\u7247\u5b8c\u6210' : '\u6b63\u5728\u7b49\u5f85\u4e0b\u4e00\u5f20\u56fe\u7247') : '\u7b49\u5f85\u4efb\u52a1\u5f00\u59cb\uff1b\u505c\u6b62\u4f1a\u5728\u5f53\u524d\u56fe\u7247\u5b8c\u6210\u540e\u751f\u6548');
  refs.batchSummary.textContent = `\u6210\u529f ${successes} \u00b7 \u9519\u8bef ${errors}`;

  state.batch.jobId = Number(safe.jobId || 0);
  state.batch.nextOffset = Number(safe.nextOffset || 0);
  state.batch.running = running;
  state.batch.completed = completed;
  state.batch.cancelRequested = cancelRequested;
  state.batch.retryMode = !!safe.retryMode;
  state.batch.status = String(safe.status || '');
  state.batch.currentFile = String(safe.currentFile || '');
  state.batch.inputDir = String(safe.inputDir || '');
  state.batch.outputDir = String(safe.outputDir || '');
  state.batch.lastError = String(safe.lastError || '');
  state.batch.failedFiles = Array.isArray(safe.failedFiles) ? safe.failedFiles : [];

  if (options.pushLogs !== false) {
    (safe.logs || []).forEach(pushLog);
  }

  renderBatchRecovery(safe);
  updateBatchButton(running, cancelRequested);
  refreshExperienceUi();
  if (running) {
    updateStatusBadge(`\u72b6\u6001: ${safe.status || '\u6279\u91cf\u5904\u7406\u4e2d'}`);
    startBatchPolling();
  } else {
    if (completed || state.batch.jobId) {
      updateStatusBadge(`\u72b6\u6001: ${safe.status || '\u6279\u91cf\u5904\u7406\u5df2\u7ed3\u675f'}`);
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

function applyPixivCurrentSnapshot(snapshot, options = {}) {
  const safe = snapshot || {};
  const running = !!safe.running;
  const completed = !!safe.completed;
  const failed = !!safe.failed;
  const draftReady = !!safe.draftReady;

  state.pixivCurrent.jobId = Number(safe.jobId || 0);
  state.pixivCurrent.nextOffset = Number(safe.nextOffset || 0);
  state.pixivCurrent.running = running;
  state.pixivCurrent.completed = completed;
  state.pixivCurrent.failed = failed;
  state.pixivCurrent.draftReady = draftReady;
  state.pixivCurrent.status = String(safe.status || '');
  state.pixivCurrent.message = String(safe.message || '');
  state.pixivCurrent.currentFile = String(safe.currentFile || '');

  if (options.pushLogs !== false) {
    (safe.logs || []).forEach(pushLog);
  }

  syncPixivFieldState();
  refreshExperienceUi();

  if (running) {
    updateStatusBadge(`\u72b6\u6001: ${safe.status || '\u5f53\u524d\u56fe\u7247\u7684 Pixiv \u4efb\u52a1\u8fdb\u884c\u4e2d'}`);
    startPixivCurrentPolling();
    return;
  }

  stopPixivCurrentPolling();
  if (completed || state.pixivCurrent.jobId) {
    updateStatusBadge(`\u72b6\u6001: ${safe.status || (failed ? '\u5f53\u524d\u56fe\u7247\u7684 Pixiv \u6d41\u7a0b\u5931\u8d25' : '\u5f53\u524d\u56fe\u7247\u7684 Pixiv \u6d41\u7a0b\u5df2\u5b8c\u6210')}`);
  }
}

function startPixivCurrentPolling() {
  if (pixivCurrentPollHandle) {
    return;
  }
  pixivCurrentPollHandle = window.setInterval(() => {
    void pollPixivCurrentStatus();
  }, 900);
  void pollPixivCurrentStatus();
}

function stopPixivCurrentPolling() {
  if (pixivCurrentPollHandle) {
    window.clearInterval(pixivCurrentPollHandle);
    pixivCurrentPollHandle = null;
  }
}

async function pollPixivCurrentStatus() {
  if (!state.pixivCurrent.jobId || state.pixivCurrent.polling || !window.pywebview?.api) {
    return;
  }

  state.pixivCurrent.polling = true;
  try {
    const result = await window.pywebview.api.poll_pixiv_upload_current(state.pixivCurrent.nextOffset || 0);
    if (!result.ok) {
      throw new Error(result.error || '杞当前图片 Pixiv 任务失败');
    }
    applyPixivCurrentSnapshot(result);
  } catch (error) {
    stopPixivCurrentPolling();
    pushLog(`当前图片 Pixiv 任务轮询失败: ${error && error.message ? error.message : error}`);
    updateStatusBadge('鐘舵€? 当前图片 Pixiv 任务轮询失败');
  } finally {
    state.pixivCurrent.polling = false;
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
    pushLog(`鎵归噺鐘舵€佽疆璇㈠け璐? ${error && error.message ? error.message : error}`);
    updateStatusBadge('状态: 批量状态轮询失败');
  } finally {
    state.batch.polling = false;
  }
}

function updateSource(payload) {
  state.source = payload;
  state.ui.lastExportedPath = '';
  refs.currentFile.textContent = payload.fileName;
  refs.currentFile.title = payload.path || payload.fileName;
  refs.sourceMeta.textContent = `${payload.fileName} - ${payload.width} x ${payload.height}`;
  refs.badgeSourceSize.textContent = `\u6e90\u56fe: ${payload.width} x ${payload.height}`;
  refs.sourceImage.src = payload.src;
  refs.sourceImage.onload = () => {
    refs.sourceStage.classList.add('active');
    refs.sourceEmpty.classList.add('hidden');
    renderRegions();
  };
  refreshExperienceUi();
}

function updatePreview(payload) {
  state.preview = payload;
  refs.resultMeta.textContent = `${payload.fileName} - ${payload.width} x ${payload.height}`;
  refs.badgePreviewSize.textContent = `\u7ed3\u679c: ${payload.width} x ${payload.height}`;
  refs.resultImage.src = payload.src;
  refs.resultImage.onload = () => {
    refs.resultStage.classList.add('active');
    refs.resultEmpty.classList.add('hidden');
  };
  refreshExperienceUi();
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
    refs.regionList.innerHTML = '<span class="hint">杩樻病鏈夐€夊尯锛岀洿鎺ュ湪婧愬浘涓婃嫋涓€鍧楀嚭鏉ュ氨琛屻€</span>';
  } else {
    state.regions.forEach((region, index) => {
      const chip = document.createElement('div');
      chip.className = 'region-chip';
      chip.innerHTML = `<span>#${index + 1} ${region.join(', ')}</span>`;

      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '脳';
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
  refreshExperienceUi();
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
    updateStatusBadge('鐘舵€? 娌℃湁鍙挙閿€鐨勯€夊尯');
    return;
  }
  const removed = state.regions.pop();
  renderRegionChips();
  renderRegions();
  updateStatusBadge('鐘舵€? 宸叉挙閿€涓婁竴涓€夊尯');
  pushLog(`撤销选区: (${removed.join(', ')})`);
}

function clearRegions() {
  if (!state.regions.length) {
    updateStatusBadge('鐘舵€? 当前没有选区');
    return;
  }
  state.regions = [];
  renderRegionChips();
  renderRegions();
  updateStatusBadge('状态: 选区已清空');
  pushLog('宸叉竻绌哄叏閮ㄩ€夊尯');
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
    updateStatusBadge('鐘舵€? 拖拽文件不受支持');
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

function showStartupOverlay(title, message, progress = '') {
  if (!refs.startupOverlay) {
    return;
  }
  refs.startupTitle.textContent = title;
  refs.startupMessage.textContent = message;
  if (refs.startupProgress) {
    refs.startupProgress.textContent = progress || '';
    refs.startupProgress.classList.toggle('hidden', !progress);
  }
  refs.startupOverlay.classList.remove('hidden');
}

function hideStartupOverlay() {
  if (!refs.startupOverlay) {
    return;
  }
  refs.startupOverlay.classList.add('hidden');
}

function getVisibleLogs() {
  return (state.ui.logs || []).filter((entry) => logMatchesFilter(entry, state.ui.logFilter || 'all'));
}

function getLogText() {
  return getVisibleLogs().map((entry) => entry.line).join('\n\n');
}

function logMatchesFilter(entry, filter) {
  const message = String(entry?.message || '');
  const normalized = message.toLowerCase();
  if (filter === 'pixiv') {
    return normalized.includes('pixiv');
  }
  if (filter === 'error') {
    return /错误|失败|error:|warning:|traceback/i.test(message);
  }
  if (filter === 'task') {
    return /寮€濮嬪理|处理完成|水印完成|打码完成|超分完成|批量|当前图片|导出|预览|已加载|载入/i.test(message);
  }
  return true;
}

function createLogElement(entry) {
  const item = document.createElement('div');
  item.className = 'log-item';
  item.innerHTML = `<time>${entry.time}</time><p>${escapeHtml(entry.message)}</p>`;
  return item;
}

function renderLogs() {
  refs.logList.innerHTML = '';
  getVisibleLogs().forEach((entry) => {
    refs.logList.appendChild(createLogElement(entry));
  });
}

async function onCopyLogs() {
  const text = getLogText();
  if (!text) {
    pushLog('暂无可复制的日志');
    return;
  }

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', 'readonly');
      helper.style.position = 'fixed';
      helper.style.opacity = '0';
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
    }
    updateStatusBadge('状态: 日志已复制');
  } catch (error) {
    pushLog(`复制日志失败: ${error && error.message ? error.message : error}`);
  }
}

function onExportLogs() {
  const text = getLogText();
  if (!text) {
    pushLog('暂无可导出的日志');
    return;
  }

  const blob = new Blob([`${text}\n`], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const stamp = new Date().toISOString().replace(/[.:]/g, '-');
  link.href = url;
  link.download = `image-workbench-log-${stamp}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  updateStatusBadge('状态: 日志已导出');
}

function pushLog(message) {
  const time = new Date().toLocaleTimeString();
  const safeMessage = String(message || '');
  state.ui.logs.unshift({
    time,
    message: safeMessage,
    line: `${time} ${safeMessage}`,
  });
  renderLogs();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}







