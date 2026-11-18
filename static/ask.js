// 「今天想做什么菜？」：输入联想 + 拍照 / 相册认菜。都是辅助：出错就退回普通表单提交
(function () {
  const input = document.getElementById('dish-input');
  const box = document.getElementById('dish-suggest');
  const askForm = document.getElementById('ask-form');
  const photoForm = document.getElementById('photo-form');
  const busy = document.getElementById('busy');
  function showBusy(text) {
    if (!busy) return;
    document.getElementById('busy-text').textContent = text;
    busy.hidden = false;
  }
  window.addEventListener('pageshow', () => { if (busy) busy.hidden = true; });  // 手机返回时别一直转圈

  // ---- 输入联想：只认「稳厨已有」的菜，不调 AI ----
  if (input && box) {
    let timer = null, seq = 0;
    const hide = () => { box.hidden = true; box.textContent = ''; };
    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (!q) { hide(); return; }
      timer = setTimeout(async () => {
        const my = ++seq;
        try {
          const r = await fetch('/dish-ai/suggest?q=' + encodeURIComponent(q));
          const data = await r.json();
          if (my !== seq) return;
          if (!data.items.length) { hide(); return; }
          box.textContent = '';
          data.items.forEach(it => {
            const a = document.createElement('a');
            a.href = it.url; a.className = 'suggest-item'; a.setAttribute('role', 'option');
            const n = document.createElement('strong'); n.textContent = it.name;
            const t = document.createElement('span'); t.className = 'tag'; t.textContent = it.kind === 'site' ? '稳厨菜谱' : '稳厨已有';
            const k = document.createElement('span'); k.className = 'kind ' + it.kind; k.textContent = it.kind === 'site' ? '直接看菜谱' : '直接看做法';
            a.append(n, t, k);
            box.appendChild(a);
          });
          box.hidden = false;
        } catch (e) { hide(); }
      }, 150);
    });
    input.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
    document.addEventListener('click', e => { if (!box.contains(e.target) && e.target !== input) hide(); });
  }
  if (askForm) {
    document.querySelectorAll('[data-dish]').forEach(a => a.addEventListener('click', e => {
      e.preventDefault();
      askForm.dish.value = a.dataset.dish;
      askForm.requestSubmit();
    }));
    askForm.addEventListener('submit', () => {
      const b = document.getElementById('ai-submit');
      if (b) { b.textContent = '正在查…（AI 最多等 20 秒）'; b.disabled = true; }
    });
  }

  // ---- 拍照 / 相册：先在手机上缩小（最长边 1280，也去掉了 EXIF），再提交给服务器认菜 ----
  function shrink(file, maxSide, quality) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
        const c = document.createElement('canvas');
        c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob(b => b ? resolve(b) : reject(new Error('toBlob')), 'image/jpeg', quality);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')); };
      img.src = url;
    });
  }
  function rememberPreview(blob) {
    // 确认页要显示一张小图：只存在这个浏览器标签页里（sessionStorage），不上传、看完就删
    return shrink(blob, 320, 0.7).then(small => new Promise(res => {
      const fr = new FileReader();
      fr.onload = () => { try { sessionStorage.setItem('wenchu-photo-preview', fr.result); } catch (e) {} res(); };
      fr.onerror = () => res();
      fr.readAsDataURL(small);
    })).catch(() => {});
  }
  if (photoForm) {
    photoForm.querySelectorAll('input[type=file]').forEach(inp => inp.addEventListener('change', async () => {
      const file = inp.files && inp.files[0];
      if (!file) return;
      photoForm.querySelectorAll('input[type=file]').forEach(o => { if (o !== inp) o.value = ''; });
      showBusy('正在认菜…（照片认完就丢）');
      try { sessionStorage.removeItem('wenchu-photo-preview'); } catch (e) {}
      try {
        const blob = await shrink(file, 1280, 0.85);
        await rememberPreview(blob);
        const dt = new DataTransfer();
        dt.items.add(new File([blob], 'photo.jpg', {type: 'image/jpeg'}));
        inp.files = dt.files;
      } catch (e) { /* 浏览器解不开（比如 HEIC）就原样交给服务器，服务器会给中文提示 */ }
      photoForm.submit();
    }));
  }
})();
