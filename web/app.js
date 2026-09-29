import {WorkspaceAPI} from './api.js';
import {CropSelection, fitMedia} from './crop.js';
import './i18n.js';

const $ = id => document.getElementById(id);
const api = new WorkspaceAPI();
const video = $('video');
video.volume = Number($('volume').value)/100;
$('review-speed').replaceChildren(...Array.from($('speed').options, option => option.cloneNode(true)));
let state = null, selected = 0, tab = 'capture', requesting = false, uploading = false;
let listSignature = '', currentMedia = '', job = null, errorShown = '', editorIndex = 0;
let polling = false, initialized = false, titleDirty = false;
let commandEpoch = 0;
let importingVideo = false, mediaLoading = false;
let aiLayoutKey = '';
let connectionResult = '';
let extractionProjectId = null;
const aiModels = {Codex:['gpt-6-astra','gpt-6-sol','gpt-6-luna'], 'Claude CLI':['sonnet','opus','haiku'], OpenAI:['gpt-6-luna','gpt-6-sol','gpt-6-astra'], DeepSeek:['deepseek-flash'], Anthropic:['claude-haiku-4-5']};
function aiConnection() {
  const provider = $('ai-provider').value, cli = ['Codex','Claude CLI'].includes(provider);
  $('ai-model').replaceChildren(...aiModels[provider].map(model => new Option(model,model)));
  $('ai-key').value = '';
  $('ai-key-field').hidden = cli;
  $('ai-connection-note').textContent = cli ? `Uses your signed-in ${provider === 'Codex' ? 'Codex' : 'Claude Code'} CLI and subscription allowance. Account limits apply.` : 'Frames and instructions are sent to this provider. API usage is billed separately; the key stays in memory.';
}
aiConnection();
function aiPageSettings() {
  return {title:$('pdf-title').value, title_first_page_only:$('ai-title-first').checked,
    subtitle:$('ai-subtitle').value, song_info:$('ai-song-info').value, show_metadata:$('ai-show-info').checked,
    footer:$('ai-footer').value, page_numbers:$('ai-page-numbers').checked,
    bars_per_line:barsOverride('ai-review-override') ? Number($('ai-review-bars').value) : 0,
    merge_rests_auto:barsOverride('ai-review-override') && $('ai-merge-rests').checked};
}
function aiConnectionPayload() { return {provider:$('ai-provider').value, model:$('ai-model').value, apiKey:$('ai-key').value}; }
function barsOverride(id) { return $(id).getAttribute('aria-pressed') === 'true'; }
function showBarsToggle(id, enabled) {
  $(id).setAttribute('aria-pressed', String(enabled));
  $(id).textContent = `Override bars per line: ${enabled ? 'ON' : 'OFF'}`;
}
const downloaded = new Set();

function fail(error) { $('error-text').textContent = error.message || String(error); $('error').hidden = false; }
function listen(id, event, callback) { $(id).addEventListener(event, e => Promise.resolve().then(() => callback(e)).catch(fail)); }
function clock(seconds, decimal = false) {
  seconds = Math.max(0, Number(seconds) || 0);
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole/60)).padStart(2,'0')}:${String(whole%60).padStart(2,'0')}${decimal ? '.'+Math.floor((seconds%1)*10) : ''}`;
}
function cropArray(region) { return [region.left, region.top, region.right, region.bottom]; }
function fitVideo() { fitMedia($('video-stage'), $('video-fit'), video.videoWidth, video.videoHeight); }
function fitEditor() { fitMedia($('editor-stage'), $('editor-fit'), $('editor-image').naturalWidth, $('editor-image').naturalHeight); }
function fitLine() {
  const img=$('line-image'), stage=$('line-stage');
  if (!img.naturalWidth || img.hidden) return;
  const style=getComputedStyle(stage), height=img.naturalHeight*(state?.lines[selected]?.height_scale || 1);
  const ratio=Math.min((stage.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight))/img.naturalWidth,
    (stage.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom))/height);
  img.style.width=`${Math.max(1,img.naturalWidth*ratio)}px`;
  img.style.height=`${Math.max(1,height*ratio)}px`;
}
function previewEdit() {
  const image=$('editor-image'), canvas=$('edited-line-preview');
  if (!image.naturalWidth) return;
  const [l,t,r,b]=editorCrop.value, width=(r-l)*image.naturalWidth, height=(b-t)*image.naturalHeight;
  const scale=Number($('line-height').value)/100;
  if (!(scale>=.25 && scale<=2)) return;
  const fit=Math.min(1,1200/width,100/(height*scale));
  canvas.width=Math.max(1,Math.round(width*fit)); canvas.height=Math.max(1,Math.round(height*scale*fit));
  canvas.getContext('2d').drawImage(image,l*image.naturalWidth,t*image.naturalHeight,width,height,0,0,canvas.width,canvas.height);
}
const crop = new CropSelection($('video-crop'), {
  moveInside: false,
  onStart: () => video.pause(),
  onEnd: value => command('region', {crop:value}).catch(fail),
});
const editorCrop = new CropSelection($('editor-crop'), {onChange: value => {
  ['left','top','right','bottom'].forEach((side,i) => $(`crop-${side}`).value = (value[i]*100).toFixed(1));
  previewEdit();
}});
new ResizeObserver(fitVideo).observe($('video-stage'));
new ResizeObserver(fitEditor).observe($('editor-stage'));
new ResizeObserver(fitLine).observe($('line-stage'));
$('line-image').addEventListener('load',fitLine);

async function command(action, data = {}) {
  const epoch = ++commandEpoch;
  requesting = true;
  updateControls();
  try {
    await api.command(action, data);
    await refresh(epoch);
  } finally { requesting = false; updateControls(); }
}
async function refresh(epoch = commandEpoch) {
  const next = await api.state();
  // A poll begun before a command must not clear its job or restore old state.
  if (epoch !== commandEpoch) return;
  const previous = state;
  state = next;
  if (next.videoId !== previous?.videoId) {
    $('ai-select-area').checked = false;
    $('bpm').value = ''; $('beats-per-bar').value = '4'; $('timing-repeats').checked = false;
    $('flexible-area').checked = false;
    $('tempo-result').hidden = true;
  }
  if (next.tempo && next.tempo.id !== previous?.tempo?.id) {
    $('bpm').value = next.tempo.bpm;
    $('tempo-result').textContent = next.tempo.consistent
      ? `Audio estimate: ${next.tempo.bpm} BPM. Check half/double tempo: ${next.tempo.alternatives.join(' / ')}.`
      : `Uncertain audio estimate: ${next.tempo.bpm} BPM. Sections disagree; enter the correct BPM manually.`;
    $('tempo-result').hidden = false;
  }
  if (next.notation && next.notation !== 'free' && next.notation !== previous?.notation) $('notation').value = next.notation;
  if (!initialized) { Object.keys(next.artifacts).forEach(key => downloaded.add(key)); initialized = true; }
  if (job === 'print-preview' && !next.busy) {
    if (!next.error) showPrintPreview();
    job=null;
  }
  if (previous?.busy && !next.busy) {
    if (job === 'extract' && !next.error && next.lines.length && next.projectId !== extractionProjectId) { selected = 0; setReviewAudio(false); switchTab('review'); }
    if (job === 'ai-edit' && !next.error) $('ai-edit-text').value = '';  // keep the request text if it failed
    job = null;
  }
  for (const [key, artifact] of Object.entries(next.artifacts)) {
    if (!downloaded.has(key)) { downloaded.add(key); api.download(key, artifact.name); }
  }
  render();
}
function switchTab(next) {
  tab = next;
  if (tab === 'review' && !$('review-audio').checked) video.pause();
  $('capture-screen').hidden = tab !== 'capture';
  $('review-screen').hidden = tab !== 'review';
  for (const name of ['capture','review']) {
    $(`${name}-tab`).classList.toggle('active', tab === name);
    $(`${name}-tab`).setAttribute('aria-selected', String(tab === name));
  }
  requestAnimationFrame(fitVideo);
}
function setReviewAudio(enabled) {
  $('keep-review-audio').checked = $('review-audio').checked = enabled;
  updateControls();
}
async function togglePlayback() {
  if (job === 'load' || importingVideo || mediaLoading) return;
  if (!state?.video || video.readyState < 2 || video.seeking) return;
  if (video.paused) {
    if (tab === 'review') setReviewAudio(true);
    await video.play();
  } else video.pause();
}
function imageUrl(index, kind = 'line') { return api.url('image', {index, kind, v:state.revision}); }
function render() {
  if (!state) return;
  const mode = state.mode === 'free' ? 'automatic' : state.mode;  // older servers report chord capture as 'free'
  const manual = mode === 'manual', ai = mode === 'ai';
  const chord = $('notation').value === 'chord';
  document.body.classList.toggle('has-video', !!state.video);
  for (const id of ['automatic','ai','manual']) $(id).setAttribute('aria-pressed', String(mode === id));
  $('free-help').hidden = !chord || mode !== 'automatic';
  $('timing-controls').hidden = chord;
  $('adaptive-controls').hidden = chord;
  $('extract').firstChild.textContent = chord ? 'Extract text lines ' : 'Extract score lines ';
  $('auto-controls').hidden = mode !== 'automatic';
  $('ai-controls').hidden = !ai;
  $('manual-controls').hidden = !manual;
  $('video-crop').hidden = ai && !$('ai-select-area').checked;
  // The capture settings panel follows whichever flow captures frames: Automatic, or AI keeping video images.
  const imagesMethod = $('ai-method').value === 'images';
  const settingsHost = ai && imagesMethod ? $('ai-capture-settings') : $('auto-capture-settings');
  if ($('advanced').parentElement !== settingsHost) settingsHost.append($('advanced'));
  $('ai-method-note').textContent = imagesMethod
    ? 'Keeps the original score images. The AI only finds the score, checks bar order and flags duplicates or broken lines — minutes, and light on your allowance.'
    : 'Reads every bar and engraves new notation you can edit with AI. Many requests; slow, but the result is uniform and editable.';
  $('ai-bars-control').hidden = $('ai-bars-note').hidden = imagesMethod;
  $('ai-instructions-step').hidden = imagesMethod;
  $('ai-page-controls').hidden = !state.ai;
  $('ai-edit-controls').hidden = !(state.ai || state.aiCheck);
  $('ai-line-transcribe').hidden = !state.aiCheck;
  const edit = state.aiEdit;
  $('ai-edit-notes').hidden = !edit;
  if (edit) $('ai-edit-notes').replaceChildren(...[
    ...(edit.marks.length ? [`Updated marks in bars ${edit.marks.join(', ')}`] : []),
    ...(edit.reread.length ? [`Re-read bars ${edit.reread.join(', ')}`] : []),
    ...edit.observations, ...edit.unsupported.map(text => `Not applied: ${text}`)]
    .map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
  for (const selector of ['.background-controls','.print-layout-controls','#reflow-help']) document.querySelector(selector).hidden = !!state.ai;
  const layoutKey = `${state.projectId}:${JSON.stringify(state.aiLayout)}`;
  if (state.ai && layoutKey !== aiLayoutKey) {
    aiLayoutKey = layoutKey;
    const layout = state.aiLayout;
    $('ai-title-first').checked = layout.title_first_page_only;
    $('ai-subtitle').value = layout.subtitle;
    $('ai-show-info').checked = layout.show_metadata;
    $('ai-song-info').value = layout.song_info || '';
    $('ai-footer').value = layout.footer;
    $('ai-page-numbers').checked = layout.page_numbers;
    showBarsToggle('ai-review-override', layout.bars_per_line > 0);
    $('ai-review-bars').value = layout.bars_per_line || 4;
    $('ai-merge-rests').checked = !!layout.merge_rests_auto;
  }
  const usage = state.aiUsage;
  $('ai-usage').hidden = !usage;
  if (usage) $('ai-usage').textContent = `${usage.requests} requests · ${usage.cache_hits} reused · ${usage.input_tokens.toLocaleString()} input / ${usage.output_tokens.toLocaleString()} output tokens · ${usage.subscription ? 'Subscription allowance' : `Estimated $${usage.estimated_usd.toFixed(4)}`}`;
  $('gap').closest('label').hidden = !!state.ai;
  if (state.aiConnection && state.aiConnection !== connectionResult) {
    connectionResult = state.aiConnection;
    $('ai-connection-note').textContent = state.aiConnection;
  }
  const mediaKey = state.video ? state.videoId : '';
  if (mediaKey !== currentMedia) {
    currentMedia = mediaKey;
    mediaLoading = !!state.video;
    if (state.video) { setReviewAudio(true); video.src = api.url('video', {v:state.revision}); video.load(); }
    else { video.pause(); video.removeAttribute('src'); video.load(); }
  }
  if (!crop.drag) crop.set(cropArray(state.region));
  $('duration').textContent = clock(state.duration);
  $('audio-note').hidden = !state.video || state.hasAudio !== false;
  $('seek').max = Math.max(0.01, state.duration-.01);
  if (!titleDirty && document.activeElement !== $('pdf-title')) $('pdf-title').value = state.title;
  const bars=state.barsPerLine || 0;
  $('background').value=state.background || 'white';
  $('original-missing').hidden=state.background !== 'original' || !state.originalMissing;
  $('reflow-bars').checked=bars>0;
  if (bars && document.activeElement !== $('bars-per-line')) $('bars-per-line').value=bars;
  $('reflow-label').hidden=$('bars-label').hidden=!['guitar','bass'].includes(state.notation);
  $('source-note').textContent = state.source || 'YouTube · MP4 · MOV · MKV · WebM · AVI';
  $('tab-count').textContent = state.lines.length;
  $('line-count').textContent = state.lines.length;
  $('manual-count').textContent = state.lines.length;
  $('included-count').textContent = state.lines.length ? `${state.lines.filter(l => l.included).length} included · in export order` : 'Capture a line to get started.';
  selected = Math.max(0, Math.min(selected, state.lines.length-1));
  const signature = `${state.projectId}:${state.mode}:${state.background}:${JSON.stringify(state.lines)}`;
  if (signature !== listSignature) { listSignature = signature; renderLines(); }
  renderSelection();
  $('warning-list').replaceChildren(...state.warnings.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
  $('warnings').hidden = !state.warnings.length;
  if (!uploading) {
    $('status').textContent = state.status;
    $('status').title = state.status;
  }
  const elapsed = state.elapsedSeconds;
  $('elapsed-time').hidden = elapsed == null;
  if (elapsed != null) {
    const seconds = Math.floor(Math.max(0, elapsed));
    $('elapsed-time').textContent = `Time taken: ${String(Math.floor(seconds/3600)).padStart(2,'0')}:${String(Math.floor(seconds/60)%60).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
  }
  $('progress').hidden = !state.busy;
  $('progress').value = state.progress;
  $('cancel').hidden = !state.busy;
  $('pause-ai').hidden = !state.busy || !state.aiPause;
  $('pause-ai').textContent = state.aiPause?.requested ? 'Resume' : 'Pause';
  $('pause-ai').title = 'Pause stops new AI requests after the current requests finish. Keep the app open to resume immediately.';
  $('pause-ai').disabled = requesting || !state.aiPause;
  $('status-dot').classList.toggle('busy', state.busy || uploading);
  if (state.error && state.error !== errorShown) { errorShown = state.error; fail(state.error); }
  if (!state.error) errorShown = '';
  updateControls();
}
function renderLines() {
  $('line-list').replaceChildren(...state.lines.map((line,index) => {
    const button = document.createElement('button');
    button.className = `line-item${line.included ? '' : ' excluded'}`;
    button.setAttribute('aria-label', `Line ${index+1}, ${line.included ? 'included' : 'excluded'}`);
    const head = document.createElement('span'); head.className = 'line-item-head';
    const title = document.createElement('span'); title.textContent = `LINE ${String(index+1).padStart(2,'0')}`;
    const tick = document.createElement('span'); tick.textContent = line.notes?.length ? '⚑' : line.included ? '✓' : '—'; head.append(title,tick);
    if (line.notes?.length) tick.title = line.notes.join('\n');
    const img = document.createElement('img'); img.src = imageUrl(index); img.alt = ''; img.loading = 'lazy';
    img.style.transform=`scaleY(${line.height_scale || 1})`;
    const kind = line.ai_bar_ids ? 'AI engraved' : ['free','chord'].includes(state.notation) ? 'Chord capture'
      : line.view ? (state.mode === 'ai' ? 'AI capture' : 'Automatic capture') : 'Manual capture';
    const note = document.createElement('small'); note.textContent = `${clock(line.time,true)} · ${kind}`;
    button.append(head,img,note);
    button.addEventListener('click', () => { selected = index; renderSelection(); updateControls(); });
    return button;
  }));
}
function renderSelection() {
  const line = state?.lines[selected];
  Array.from($('line-list').children).forEach((button,i) => button.setAttribute('aria-pressed', String(i===selected)));
  $('line-empty').hidden = !!line;
  $('line-image').hidden = !line;
  $('preview-title').textContent = line ? `Line ${String(selected+1).padStart(2,'0')}` : 'Line preview';
  if (line) {
    const key = `${state.projectId}:${state.mode}:${state.background}:${selected}:${line.path}`;
    if ($('line-image').dataset.key !== key) { $('line-image').src = imageUrl(selected); $('line-image').dataset.key = key; }
    $('include-line').textContent = 'Exclude line';
    $('line-meta').textContent = `${clock(line.time,true)} · ${line.included ? 'Included in PDF' : 'Excluded from PDF'}`;
    requestAnimationFrame(fitLine);
  }
  $('line-notes').hidden = !line?.notes?.length;
  if (line?.notes?.length) $('line-notes').textContent = line.notes.join(' · ');
}
function updateControls() {
  const loadingVideo = job === 'load' || importingVideo || mediaLoading;
  $('video-loading').hidden = !loadingVideo;
  $('video-empty').hidden = loadingVideo || !!state?.video;
  $('video-fit').hidden = loadingVideo || !state?.video;
  $('video-stage').setAttribute('aria-busy', String(loadingVideo));
  const locked = !state || state.busy || requesting || uploading;
  const loaded = !!state?.video;
  const line = state?.lines[selected];
  const ready = loaded && video.readyState >= 2 && !video.seeking;
  const conditions = {
    'load-video':!!$('source').value.trim(), 'choose-video':true, 'open-project':true,
    automatic:true, ai:true, manual:true, detect:ready, extract:loaded, 'ai-extract':loaded, layout:true, play:ready,
    'detect-tempo':loaded && state.hasAudio, bpm:true, 'beats-per-bar':true, 'timing-repeats':true, 'flexible-area':true,
    'add-line':ready, speed:loaded, mute:loaded && state.hasAudio !== false, volume:loaded && state.hasAudio !== false,
    'keep-review-audio':loaded && state.hasAudio !== false, 'review-audio':loaded && state.hasAudio !== false,
    'review-play':ready && state.hasAudio !== false && $('review-audio').checked,
    'review-speed':loaded && state.hasAudio !== false && $('review-audio').checked,
    'edit-line':!!line && !state.ai && !line.ai_bar_ids, 'include-line':!!line, 'duplicate-line':!!line, 'move-up':!!line && selected>0,
    'ai-line-transcribe':!!state?.aiCheck && !!line && !['free','chord'].includes(state.notation), 'ai-method':true,
    'undo-line':!!state?.canUndo,
    'move-down':!!line && selected<state.lines.length-1,
    'save-project':!!state?.lines.length, 'export-pdf':!!state?.lines.some(l => l.included),
    'preview-print':!!state?.lines.some(l=>l.included), 'reflow-bars':!!state?.lines.length && ['guitar','bass'].includes(state.notation),
    'bars-per-line':!!state?.barsPerLine,
    'for-print':true, notation:true,
    background:!!state?.lines.length,
    'ai-provider':true, 'ai-model':true, 'ai-key':true, 'ai-check':true, 'ai-instructions':true,
    'ai-select-area':loaded,
    'ai-override-bars':$('notation').value !== 'chord', 'ai-bars':barsOverride('ai-override-bars') && $('notation').value !== 'chord',
    'ai-review-override':!!state?.ai && state.notation !== 'chord', 'ai-review-bars':!!state?.ai && barsOverride('ai-review-override') && state.notation !== 'chord',
    'ai-merge-rests':!!state?.ai && barsOverride('ai-review-override') && state.notation !== 'chord',
    'ai-apply-layout':!!state?.ai, 'ai-preview':!!state?.ai && !!state?.lines.length,
    'ai-edit-text':!!state?.ai, 'ai-edit-apply':!!state?.ai && !!$('ai-edit-text').value.trim(),
  };
  for (const [id, enabled] of Object.entries(conditions)) $(id).disabled = locked || !enabled;
  $('seek').disabled = locked || !loaded;
  crop.enabled = !locked && ready;
  $('pdf-title').disabled = locked;
}
async function choose(kind) {
  if (window.desktop) {
    const path = await api.choose(kind);
    if (!path) return;
    if (kind === 'video') { $('source').value = path; updateControls(); }
    else { video.pause(); titleDirty = false; await command('open', {path}); selected = 0; switchTab('review'); }
  } else $(kind === 'video' ? 'video-file' : 'project-file').click();
}
async function upload(file, kind) {
  if (!file) return;
  uploading = true; importingVideo = kind === 'video'; updateControls();
  try {
    const path = await api.upload(file, fraction => $('status').textContent = `Importing ${file.name} · ${Math.round(fraction*100)}%`);
    if (kind === 'video') { $('source').value = path; await loadVideo(); }
    else { video.pause(); titleDirty = false; await command('open', {path}); switchTab('review'); }
  } finally { uploading = false; importingVideo = false; updateControls(); }
}
async function loadVideo() {
  video.pause(); job = 'load'; titleDirty = false;
  try {
    await command('load', {source:$('source').value, layout:$('layout').value, notation:$('notation').value});
    // A cached/local video can finish before polling ever sees a busy state.
    if (!state?.busy) job = null;
  } catch (error) { job = null; throw error; }
  finally { updateControls(); }
}
listen('capture-tab','click', () => switchTab('capture'));
listen('review-tab','click', () => switchTab('review'));
listen('review-lines','click', () => switchTab('review'));
listen('back-capture','click', () => switchTab('capture'));
listen('dismiss-error','click', () => $('error').hidden = true);
listen('source','input', updateControls);
listen('source','keydown', e => { if (e.key === 'Enter' && !$('load-video').disabled) return loadVideo(); });
listen('choose-video','click', () => choose('video'));
listen('open-project','click', () => choose('project'));
listen('video-file','change', e => upload(e.target.files[0], 'video'));
listen('project-file','change', e => upload(e.target.files[0], 'project'));
listen('load-video','click', loadVideo);
for (const mode of ['automatic','ai','manual']) listen(mode,'click', async () => {
  video.pause(); selected = 0;
  await command('mode', {mode});
  if (mode === 'manual') setReviewAudio(true);
});
listen('ai-select-area','change', render);
listen('ai-method','change', () => { if (state) render(); });
listen('ai-line-transcribe','click', () => { video.pause(); return command('ai-line-transcribe', {index:selected, ...aiConnectionPayload()}); });
listen('detect','click', () => { video.pause(); return command('detect', {time:video.currentTime, layout:$('layout').value, notation:$('notation').value}); });
listen('detect-tempo','click', () => { video.pause(); return command('detect-tempo'); });
listen('bpm','input', () => { $('tempo-result').hidden = true; });
listen('notation','change', async () => {
  if (state) render();
  // Automatic capture re-detects the score area for the chosen instrument.
  if (state?.video && state.mode === 'automatic' && $('notation').value !== 'chord') {
    video.pause();
    await command('detect', {time:video.currentTime, layout:$('layout').value, notation:$('notation').value});
  }
});
listen('notation','change', () => { $('ai-bars-note').textContent = $('notation').value === 'chord' ? 'Chord and lyric sheets preserve visible text rows; musical bar counts do not apply.' : "Off: follow the video's original row breaks. Uncertain breaks are reported for review."; updateControls(); });
listen('ai-provider','change',aiConnection);
listen('ai-check','click',()=>command('ai-check',{provider:$('ai-provider').value}));
for (const id of ['ai-override-bars','ai-review-override']) listen(id,'click',()=>{
  showBarsToggle(id, !barsOverride(id));
  // Rearranged rows merge rest runs by default; following the video never does.
  if (id === 'ai-review-override' && barsOverride(id)) $('ai-merge-rests').checked = true;
  updateControls();
});
listen('ai-show-info','change',updateControls);
listen('ai-song-info','input',()=>{$('ai-show-info').checked=!!$('ai-song-info').value;});
listen('ai-apply-layout','click',()=>command('ai-layout',{layout:aiPageSettings()}));
listen('ai-edit-text','input',updateControls);
listen('ai-edit-apply','click', async () => {
  const text = $('ai-edit-text').value.trim();
  if (!text) return;
  video.pause(); job = 'ai-edit';
  try { await command('ai-edit', {text, ...aiConnectionPayload()}); if (!state?.busy) job = null; }
  catch (error) { job = null; throw error; }
});
listen('ai-preview','click',()=>{job='print-preview';return command('ai-preview',{layout:aiPageSettings(),paper:$('paper').value,left:$('left-margin').value,right:$('right-margin').value});});
listen('extract','click', async () => {
  video.pause(); setReviewAudio(false); job = 'extract';
  extractionProjectId = state.projectId;
  try {
    await command('extract', {interval:$('interval').value, threshold:$('threshold').value, start:$('start').value,
      end:$('end').value, overlap:true, layout:$('layout').value, notation:$('notation').value,
      bpm:$('bpm').value ? Number($('bpm').value) : null, beatsPerBar:Number($('beats-per-bar').value) || 4,
      timingRepeats:$('timing-repeats').checked, flexibleArea:$('flexible-area').checked});
    if (!state.busy && !state.error && state.lines.length && state.projectId !== extractionProjectId) {selected=0;switchTab('review');job=null;}
  } catch(error) {job=null;throw error;}
});
listen('ai-extract','click', async () => {
  if (barsOverride('ai-override-bars') && !$('ai-bars').reportValidity()) return;
  video.pause(); setReviewAudio(false); job = 'extract';
  extractionProjectId = state.projectId;
  try {
    await command('ai-extract', {...aiConnectionPayload(), method:$('ai-method').value,
      interval:$('interval').value, threshold:$('threshold').value, start:$('start').value, end:$('end').value, overlap:true,
      instrument:$('notation').value === 'staff' ? 'drums' : $('notation').value,
      bars:barsOverride('ai-override-bars') && $('notation').value !== 'chord' ? Number($('ai-bars').value) : 0,
      instructions:$('ai-instructions').value,
      crop:$('ai-select-area').checked ? cropArray(state.region) : null});
    if (!state.busy && !state.error && state.lines.length && state.projectId !== extractionProjectId) {selected=0;switchTab('review');job=null;}
  } catch(error) {job=null;throw error;}
});
listen('cancel','click', () => command('cancel'));
listen('pause-ai','click', () => command(state.aiPause?.requested ? 'resume-ai' : 'pause-ai'));
listen('play','click', togglePlayback);
listen('review-play','click', togglePlayback);
for (const id of ['speed','review-speed']) listen(id,'change', () => {
  const value = $(id).value;
  $('speed').value = $('review-speed').value = value;
  video.playbackRate = Number(value);
});
for (const id of ['keep-review-audio','review-audio']) listen(id,'change', async () => {
  const enabled = $(id).checked;
  setReviewAudio(enabled);
  if (tab === 'review') {
    if (enabled) await video.play();
    else video.pause();
  }
});
listen('mute','click', () => {
  if (video.muted || video.volume === 0) {
    video.muted = false;
    if (video.volume === 0) video.volume = .7;
  } else video.muted = true;
});
listen('volume','input', () => { video.volume = Number($('volume').value)/100; video.muted = false; });
video.addEventListener('volumechange', () => {
  const muted = video.muted || video.volume === 0;
  $('mute').textContent = muted ? 'Unmute' : 'Mute';
  $('mute').setAttribute('aria-label', muted ? 'Unmute audio' : 'Mute audio');
  $('mute').setAttribute('aria-pressed', String(muted));
  $('volume').value = Math.round(video.volume*100);
  $('volume-value').textContent = video.muted ? 'Muted' : `${Math.round(video.volume*100)}%`;
});
listen('add-line','click', async () => { selected = state.lines.length; await command('capture', {time:video.currentTime}); });
listen('seek','input', () => { video.pause(); video.currentTime = Number($('seek').value); $('current-time').textContent = clock(video.currentTime,true); });
video.addEventListener('timeupdate', () => { $('seek').value = video.currentTime; $('current-time').textContent = clock(video.currentTime,true); });
video.addEventListener('loadedmetadata', () => { video.playbackRate = Number($('speed').value); video.currentTime = state.mode === 'manual' ? 0 : Math.min(20, state.duration*.1); fitVideo(); });
function playbackButtons() {
  for (const id of ['play','review-play']) {
    const icon = document.createElement('span');
    icon.className = `playback-icon ${video.paused ? 'play-icon' : 'pause-icon'}`;
    icon.setAttribute('aria-hidden','true');
    const label = document.createElement('span'); label.textContent = video.paused ? 'Play' : 'Pause';
    $(id).replaceChildren(icon,label);
  }
}
playbackButtons();
for (const event of ['loadeddata','seeked','seeking','play','pause','ended']) video.addEventListener(event, () => { playbackButtons(); updateControls(); });
video.addEventListener('loadeddata', () => { mediaLoading = false; updateControls(); fitVideo(); });
video.addEventListener('error', () => { mediaLoading = false; updateControls(); if (video.getAttribute('src')) fail('This video could not be played. Reload it or try an H.264 MP4 file.'); });
listen('pdf-title','input', () => { titleDirty = true; });
listen('for-print','click', () => {
  $('gap').value = '0';
  $('left-margin').value = $('right-margin').value = '12';
});
listen('include-line','click', () => command('remove', {index:selected}));
listen('duplicate-line','click', async () => {
  const index = selected;
  await command('duplicate', {index});
  selected = index + 1;
  renderSelection();
  updateControls();
  $('line-list').children[selected]?.scrollIntoView({block:'nearest'});
});
listen('undo-line','click', async () => {
  selected = state.undoIndex;
  await command('undo');
});
for (const [id,direction] of [['move-up',-1],['move-down',1]]) listen(id,'click', async () => {
  const index = selected; selected += direction;
  try { await command('move', {index,direction}); } catch (error) { selected = index; throw error; }
});
listen('save-project','click', () => { video.pause(); job = 'save'; return command('save', {title:$('pdf-title').value, aiLayout:state.ai ? aiPageSettings() : null}); });
async function setPrintSettings() {
  if ($('reflow-bars').checked && !$('bars-per-line').reportValidity()) return;
  await command('print-settings',{bars:$('reflow-bars').checked?Number($('bars-per-line').value):0});
}
listen('reflow-bars','change',setPrintSettings);
listen('background','change',()=>command('background',{background:$('background').value}));
listen('advanced','toggle',()=>$('advanced').querySelector('summary').setAttribute('aria-expanded',String($('advanced').open)));
listen('bars-per-line','change',setPrintSettings);
listen('preview-print','click',()=>{video.pause();job='print-preview';return command('preview-print');});
  listen('close-print-preview','click',()=>$('print-preview').close());
  const printDialog=$('print-preview');
  const outsidePreview=event=>{
    const bounds=printDialog.getBoundingClientRect();
    return event.target===printDialog && (event.clientX<bounds.left || event.clientX>bounds.right || event.clientY<bounds.top || event.clientY>bounds.bottom);
  };
  let backdropDown=false;
  printDialog.addEventListener('pointerdown',event=>{backdropDown=outsidePreview(event);});
  printDialog.addEventListener('pointerup',event=>{
    if (backdropDown && outsidePreview(event)) printDialog.close();
    backdropDown=false;
  });
  printDialog.addEventListener('pointercancel',()=>{backdropDown=false;});
  let previewFocus=null;
  printDialog.addEventListener('close',()=>{if(job==='print-preview') job=null;previewFocus=null;});
  function showPrintPreview() {
  const preview=state.printPreview;
  if (!preview) return;
  $('print-preview-title').textContent=preview.pages ? 'Preview PDF' : 'Print lines';
  $('print-preview-summary').textContent=`${preview.widths.length} ${preview.pages ? 'PDF pages' : 'print lines'}`;
  $('print-preview-notes').replaceChildren(...preview.notes.map(note=>{const p=document.createElement('p');p.textContent=note;return p;}));
  $('print-preview-rows').replaceChildren(...preview.widths.map((width,index)=>{
    const row=document.createElement('div'), label=document.createElement('span'), img=document.createElement('img');
    label.textContent=`${preview.pages ? 'Page' : 'Line'} ${String(index+1).padStart(2,'0')}`;
      img.src=api.url('print-row',{index,id:preview.id});img.alt=label.textContent;img.loading='lazy';img.style.width=`${width*100}%`;
      [img.width,img.height]=preview.sizes[index];
      const header=document.createElement('div');header.className='print-row-header';header.append(label);
      if (preview.anchors[index]) {
        const field=document.createElement('label'), caption=document.createElement('span'), select=document.createElement('select');
        caption.textContent='Bars on this line';
        select.setAttribute('aria-label',`Bars on line ${index+1}`);
        select.dataset.anchor=preview.anchors[index];
        select.add(new Option(`Default (${state.barsPerLine})`,'0'));
        for (let bars=1;bars<=16;bars++) select.add(new Option(String(bars),String(bars)));
        select.value=String(preview.overrides[index]);
        select.addEventListener('change',async()=>{
          previewFocus={anchor:preview.anchors[index],top:select.getBoundingClientRect().top};
          $('print-preview-rows').querySelectorAll('select').forEach(input=>{input.disabled=true;});
          try {
            await command('print-line-bars',{anchor:preview.anchors[index],bars:Number(select.value)});
            job='print-preview';await command('preview-print');
          } catch(error) {job=null;fail(error);$('print-preview-rows').querySelectorAll('select').forEach(input=>{input.disabled=false;});}
        });
        field.append(caption,select);header.append(field);
      }
      row.append(header,img);return row;
    }));
    if (!printDialog.open) printDialog.showModal();
    if (previewFocus) {
      const select=printDialog.querySelector(`select[data-anchor="${previewFocus.anchor}"]`);
      if (select) {printDialog.scrollTop+=select.getBoundingClientRect().top-previewFocus.top;select.focus({preventScroll:true});}
      previewFocus=null;
    }
}
listen('export-pdf','click', () => { video.pause(); job = 'export'; return command('export', {title:$('pdf-title').value, paper:$('paper').value,
  gap:$('gap').value, left:$('left-margin').value, right:$('right-margin').value, aiLayout:state.ai ? aiPageSettings() : null}); });
listen('edit-line','click', () => {
  editorIndex = selected;
  const line = state.lines[selected];
  $('line-height').value=String(Math.round((line.height_scale || 1)*100));
  $('all-line-heights').checked=false;
  $('editor-title').textContent = `Edit line ${String(selected+1).padStart(2,'0')}`;
  $('editor-hint').textContent = line.source_path ? 'Drag the corners to crop or expand into the original frame. Drag inside to move the selection.' : 'This older project contains only the captured image. Crop it here; expansion is limited to its original edges.';
  $('editor-image').src = imageUrl(selected,'source');
  editorCrop.set(line.crop || [0,0,1,1]);
  $('editor').showModal();
  requestAnimationFrame(fitEditor);
});
$('editor-image').addEventListener('load', fitEditor);
$('editor-image').addEventListener('load',previewEdit);
listen('line-height','input',previewEdit);
for (const id of ['close-editor','cancel-edit']) listen(id,'click', () => $('editor').close());
for (const side of ['left','top','right','bottom']) listen(`crop-${side}`,'change', () => {
  const value = ['left','top','right','bottom'].map(s => Number($(`crop-${s}`).value)/100);
  if (value.every(Number.isFinite) && value[0]>=0 && value[1]>=0 && value[2]<=1 && value[3]<=1 && value[2]>value[0] && value[3]>value[1]) editorCrop.set(value);
  else { editorCrop.set(editorCrop.value); throw new Error('Crop edges must form a rectangle within 0–100%.'); }
});
listen('apply-edit','click', async () => {
  if (!$('line-height').reportValidity()) return;
  $('apply-edit').disabled = true;
  try { await command('edit', {index:editorIndex,crop:editorCrop.value,heightScale:Number($('line-height').value)/100,allHeights:$('all-line-heights').checked}); $('editor').close(); }
  finally { $('apply-edit').disabled = false; }
});
listen('reset-line','click', async () => { await command('edit', {index:editorIndex,reset:true}); $('editor').close(); });
document.addEventListener('keydown', e => {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  // Keep spaces available for titles/URLs, but never activate a focused action button.
  if (e.code === 'Space' && !e.target.closest('textarea,[contenteditable]:not([contenteditable="false"]),input:not([type=range],[type=checkbox],[type=number])')) {
    e.preventDefault();
    if (!e.repeat) togglePlayback().catch(fail);
    return;
  }
  if (
      e.target.closest('input,select,textarea,[contenteditable]:not([contenteditable="false"])') ||
      $('editor').open || $('print-preview').open || state?.busy || requesting || uploading) return;
  const direction = {ArrowUp:-1, ArrowLeft:-1, ArrowDown:1, ArrowRight:1}[e.key];
  if (tab === 'review' && direction && state?.lines.length) {
    e.preventDefault();
    selected = Math.max(0, Math.min(selected + direction, state.lines.length - 1));
    renderSelection();
    updateControls();
    const button = $('line-list').children[selected];
    button.focus({preventScroll:true});
    button.scrollIntoView({block:'nearest',inline:'nearest'});
    return;
  }
});
async function poll() {
  if (!polling && !requesting && !$('editor').open) {
    polling = true;
    try { await refresh(); } catch (error) { $('status').textContent = 'Connection lost. Reopen the app to reconnect.'; if (!initialized) fail(error); }
    finally { polling = false; }
  }
  setTimeout(poll, state?.busy ? 350 : 900);
}
updateControls();
poll();
