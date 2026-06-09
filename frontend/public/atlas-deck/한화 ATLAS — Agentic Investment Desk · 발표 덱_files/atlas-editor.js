(() => {
  const STORAGE_KEY = 'hanwha-atlas-deck-edit-v22';
  let selected = null;
  let moveMode = false;
  let dirtyTimer = null;

  const componentSelector = [
    '.card', '.shot', '.logoslot', '.pill', '.tag', '.iconslot', '.row', '.metric',
    '.accent-bar', '.brandmark', '.bignum', '.atlas-added-component', '.atlas-added-text'
  ].join(',');
  const textSelector = [
    '.s-title', '.s-lead', '.kicker', '.pill', '.tag', '.mono', '.brandmark', '.cap',
    '.logoslot', '.iconslot', '.disp', '.metric', '.rt', '.rd', '.rn', '.num', '.pageno',
    '.card div', '.card span', '.row span', '.row div', '.s-foot span'
  ].join(',');

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function stage() { return $('deck-stage'); }
  function sections() { return $$('deck-stage > section'); }

  function installToolbar() {
    const bar = document.createElement('div');
    bar.className = 'atlas-editor-toolbar';
    bar.innerHTML = `
      <strong>ATLAS Editor</strong>
      <button type="button" data-action="toggle" class="is-active">편집 ON</button>
      <button type="button" data-action="move">이동 모드</button>
      <button type="button" data-action="addText">텍스트 추가</button>
      <button type="button" data-action="addCard">카드 추가</button>
      <button type="button" data-action="duplicate">복제</button>
      <button type="button" data-action="delete">삭제</button>
      <button type="button" data-action="bringFront">앞으로</button>
      <button type="button" data-action="save">저장</button>
      <button type="button" data-action="reset">초기화</button>
      <button type="button" data-action="download">HTML 다운로드</button>
      <span class="atlas-editor-status">텍스트는 클릭 후 바로 수정 · 컴포넌트는 선택 후 이동 모드에서 드래그</span>
    `;
    document.body.prepend(bar);
    bar.addEventListener('click', onToolbarClick);

    const hint = document.createElement('div');
    hint.className = 'atlas-editor-hint';
    hint.textContent = '사용법: 텍스트를 클릭해 직접 수정하세요. 카드/슬롯/태그를 클릭하면 선택됩니다. 이동 모드를 켜고 드래그하면 위치를 옮길 수 있습니다. 변경사항은 자동 저장됩니다.';
    document.body.appendChild(hint);
  }

  function onToolbarClick(e) {
    const action = e.target?.dataset?.action;
    if (!action) return;
    if (action === 'toggle') toggleEdit(e.target);
    if (action === 'move') toggleMove(e.target);
    if (action === 'addText') addText();
    if (action === 'addCard') addCard();
    if (action === 'duplicate') duplicateSelected();
    if (action === 'delete') deleteSelected();
    if (action === 'bringFront') bringFront();
    if (action === 'save') saveNow(true);
    if (action === 'reset') resetAll();
    if (action === 'download') downloadHtml();
  }

  function toggleEdit(btn) {
    document.body.classList.toggle('atlas-edit-mode');
    const on = document.body.classList.contains('atlas-edit-mode');
    btn.classList.toggle('is-active', on);
    btn.textContent = on ? '편집 ON' : '편집 OFF';
    markEditable();
  }

  function toggleMove(btn) {
    moveMode = !moveMode;
    btn.classList.toggle('is-active', moveMode);
  }

  function markEditable() {
    const on = document.body.classList.contains('atlas-edit-mode');
    $$(textSelector, stage()).forEach(el => {
      if (el.closest('image-slot') || el.matches('section, deck-stage')) return;
      const hasUsefulText = (el.textContent || '').trim().length > 0;
      if (!hasUsefulText) return;
      el.dataset.atlasText = 'true';
      el.contentEditable = on ? 'true' : 'false';
      el.spellcheck = false;
    });
    $$(componentSelector, stage()).forEach(el => {
      if (el.closest('image-slot')) return;
      el.dataset.atlasComponent = 'true';
    });
  }

  function restore() {
    const html = localStorage.getItem(STORAGE_KEY);
    if (html && stage()) stage().innerHTML = html;
  }

  function serializeStage() {
    const root = stage().cloneNode(true);
    root.querySelectorAll('[contenteditable]').forEach(el => el.removeAttribute('contenteditable'));
    root.querySelectorAll('[data-atlas-selected], [data-atlas-dragging]').forEach(el => {
      el.removeAttribute('data-atlas-selected');
      el.removeAttribute('data-atlas-dragging');
    });
    return root.innerHTML;
  }

  function scheduleSave() {
    clearTimeout(dirtyTimer);
    dirtyTimer = setTimeout(() => saveNow(false), 450);
  }

  function saveNow(toast = false) {
    localStorage.setItem(STORAGE_KEY, serializeStage());
    setStatus(toast ? '저장 완료' : '자동 저장됨');
  }

  function setStatus(msg) {
    const status = $('.atlas-editor-status');
    if (status) status.textContent = msg;
  }

  function select(el) {
    if (selected) selected.removeAttribute('data-atlas-selected');
    selected = el;
    if (selected) {
      selected.dataset.atlasSelected = 'true';
      const label = selected.className ? `.${String(selected.className).replace(/\s+/g, '.')}` : selected.tagName.toLowerCase();
      setStatus(`선택됨: ${label}`);
    }
  }

  function currentSection() {
    return selected?.closest('section') || sections()[0];
  }

  function addText() {
    const sec = currentSection();
    const el = document.createElement('div');
    el.className = 's-lead atlas-added-text';
    el.textContent = '새 텍스트를 입력하세요';
    el.style.fontSize = sec.classList.contains('s--dark') ? '34px' : '30px';
    el.style.color = sec.classList.contains('s--dark') ? 'var(--beige)' : 'var(--espresso)';
    sec.appendChild(el);
    markEditable();
    select(el);
    el.focus();
    scheduleSave();
  }

  function addCard() {
    const sec = currentSection();
    const el = document.createElement('div');
    el.className = 'card hot atlas-added-component';
    el.innerHTML = '<div class="mono" style="font-size:20px;color:#C2570F;font-weight:700">NEW COMPONENT</div><div style="font-family:var(--font-head);font-weight:700;font-size:32px;margin-top:12px;color:var(--espresso)">새 카드 제목</div><div style="font-size:21px;color:var(--espresso-2);margin-top:10px;line-height:1.45">설명을 자유롭게 수정하세요.</div>';
    if (sec.classList.contains('s--dark')) {
      el.style.background = 'rgba(255,255,255,.055)';
      el.style.borderColor = 'rgba(243,115,33,.32)';
      el.querySelectorAll('div')[1].style.color = 'var(--beige)';
      el.querySelectorAll('div')[2].style.color = 'var(--greige)';
    }
    sec.appendChild(el);
    markEditable();
    select(el);
    scheduleSave();
  }

  function duplicateSelected() {
    if (!selected) return setStatus('복제할 컴포넌트를 먼저 선택하세요');
    const clone = selected.cloneNode(true);
    clone.removeAttribute('data-atlas-selected');
    const x = parseInt(selected.style.getPropertyValue('--atlas-x') || '0', 10) + 28;
    const y = parseInt(selected.style.getPropertyValue('--atlas-y') || '0', 10) + 28;
    clone.style.setProperty('--atlas-x', `${x}px`);
    clone.style.setProperty('--atlas-y', `${y}px`);
    selected.after(clone);
    markEditable();
    select(clone);
    scheduleSave();
  }

  function deleteSelected() {
    if (!selected) return setStatus('삭제할 컴포넌트를 먼저 선택하세요');
    if (!confirm('선택한 요소를 삭제할까요?')) return;
    const next = selected.closest('section');
    selected.remove();
    selected = null;
    setStatus(next?.dataset?.screenLabel || '삭제 완료');
    scheduleSave();
  }

  function bringFront() {
    if (!selected) return setStatus('앞으로 보낼 컴포넌트를 먼저 선택하세요');
    const current = Number(getComputedStyle(selected).zIndex);
    selected.style.zIndex = String(Number.isFinite(current) ? current + 10 : 100);
    scheduleSave();
  }

  function resetAll() {
    if (!confirm('저장된 편집 내용을 모두 지우고 원본으로 되돌릴까요?')) return;
    localStorage.removeItem(STORAGE_KEY);
    location.reload();
  }

  function downloadHtml() {
    saveNow(false);
    const clone = document.documentElement.cloneNode(true);
    clone.querySelector('.atlas-editor-toolbar')?.remove();
    clone.querySelector('.atlas-editor-hint')?.remove();
    clone.querySelectorAll('[contenteditable]').forEach(el => el.removeAttribute('contenteditable'));
    clone.querySelectorAll('[data-atlas-selected], [data-atlas-dragging]').forEach(el => {
      el.removeAttribute('data-atlas-selected');
      el.removeAttribute('data-atlas-dragging');
    });
    const blob = new Blob(['<!DOCTYPE html>\n' + clone.outerHTML], { type: 'text/html;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '한화 ATLAS 발표덱_edited.html';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function installSelectionAndDrag() {
    stage().addEventListener('input', scheduleSave, true);
    stage().addEventListener('click', (e) => {
      if (!document.body.classList.contains('atlas-edit-mode')) return;
      const component = e.target.closest('[data-atlas-component]');
      if (component && stage().contains(component)) {
        select(component);
      }
    }, true);

    stage().addEventListener('pointerdown', (e) => {
      if (!document.body.classList.contains('atlas-edit-mode') || !moveMode) return;
      const component = e.target.closest('[data-atlas-component]');
      if (!component || !stage().contains(component)) return;
      select(component);
      e.preventDefault();
      component.dataset.atlasDragging = 'true';
      const startX = e.clientX;
      const startY = e.clientY;
      const baseX = parseFloat(component.style.getPropertyValue('--atlas-x') || '0');
      const baseY = parseFloat(component.style.getPropertyValue('--atlas-y') || '0');
      const scale = component.closest('deck-stage')?.getBoundingClientRect().width / 1920 || 1;
      const onMove = (ev) => {
        component.style.setProperty('--atlas-x', `${baseX + (ev.clientX - startX) / scale}px`);
        component.style.setProperty('--atlas-y', `${baseY + (ev.clientY - startY) / scale}px`);
      };
      const onUp = () => {
        component.removeAttribute('data-atlas-dragging');
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        scheduleSave();
      };
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp, { once: true });
    }, true);
  }

  function boot() {
    restore();
    document.body.classList.add('atlas-edit-mode');
    installToolbar();
    markEditable();
    installSelectionAndDrag();
    setStatus('준비 완료: 텍스트 클릭 수정 / 컴포넌트 선택 / 이동 모드 드래그');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();





















