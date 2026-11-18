(() => {
  const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const mobile = window.matchMedia('(max-width: 700px)').matches || /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  if (standalone || !mobile) return;

  const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  let installPrompt = null;

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'pwa-install-trigger';
  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.innerHTML = '<span aria-hidden="true">＋</span> 添加到主屏幕';

  const guide = document.createElement('div');
  guide.className = 'pwa-install-backdrop';
  guide.hidden = true;
  guide.innerHTML = `
    <section class="pwa-install-dialog" role="dialog" aria-modal="true" aria-labelledby="pwa-install-title">
      <button type="button" class="pwa-install-close" aria-label="关闭">×</button>
      <span class="pwa-install-kicker">手机优先 · 稳厨随手可开</span>
      <h2 id="pwa-install-title">把稳厨放到手机桌面</h2>
      <p class="pwa-install-intro">添加后会出现“稳厨”图标；从桌面打开时以独立窗口运行，隐藏浏览器地址栏，不用经过应用商店。</p>
      <ol class="pwa-install-steps"></ol>
      <p class="pwa-install-note"></p>
    </section>`;

  const steps = guide.querySelector('.pwa-install-steps');
  const note = guide.querySelector('.pwa-install-note');
  if (ios) {
    ['请在 Safari 中打开这个页面（如果你现在在其他 App 里，请先用 Safari 打开预览网址）。', '点 Safari 工具栏里的“分享”按钮。', '向下滑动并点“添加到主屏幕”，再点右上角“添加”。'].forEach(text => {
      const item = document.createElement('li');
      item.textContent = text;
      steps.append(item);
    });
    note.textContent = '添加后，从 iPhone 桌面的“稳厨”图标即可在独立窗口中打开；手机系统状态栏仍由 iOS 显示。';
  } else {
    ['点浏览器菜单（⋮ 或分享图标）。', '选择“安装应用”或“添加到主屏幕”。', '确认添加；完成后可从桌面上的“稳厨”图标打开。'].forEach(text => {
      const item = document.createElement('li');
      item.textContent = text;
      steps.append(item);
    });
    note.textContent = '部分 Android 浏览器会直接弹出系统安装确认。';
  }

  const closeButton = guide.querySelector('.pwa-install-close');
  const closeGuide = () => {
    guide.hidden = true;
    trigger.focus();
  };
  trigger.addEventListener('click', async () => {
    if (installPrompt) {
      const prompt = installPrompt;
      installPrompt = null;
      await prompt.prompt();
      const result = await prompt.userChoice;
      if (result && result.outcome === 'accepted') trigger.hidden = true;
      return;
    }
    guide.hidden = false;
    closeButton.focus();
  });
  closeButton.addEventListener('click', closeGuide);
  guide.addEventListener('click', event => {
    if (event.target === guide) closeGuide();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !guide.hidden) closeGuide();
  });
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
  });
  window.addEventListener('appinstalled', () => {
    trigger.hidden = true;
    guide.hidden = true;
  });

  document.body.append(trigger, guide);
})();
