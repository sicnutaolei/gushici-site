/* 拾遗集 —— 主题切换与自定义主色/背景色
 * 预设：light / dark / green / system（跟随系统）
 * 自定义：accent（覆盖 --vermilion 等强调色）、bg（覆盖 --paper/--card）
 * 全部存于 localStorage，键名 gushi-theme / gushi-accent / gushi-bg
 */
(function () {
  var root = document.documentElement;
  var KEY_T = 'gushi-theme', KEY_A = 'gushi-accent', KEY_B = 'gushi-bg';
  var toggle = document.getElementById('themeToggle');
  var panel = document.getElementById('themePanel');
  var opts = document.getElementById('themeOpts');
  var accent = document.getElementById('accentPicker');
  var bg = document.getElementById('bgPicker');
  var reset = document.getElementById('themeReset');
  if (!toggle || !panel) return;

  function mix(a, b, r) {
    var pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    var ar = pa >> 16, ag = (pa >> 8) & 255, ab = pa & 255;
    var br = pb >> 16, bgc = (pb >> 8) & 255, bb = pb & 255;
    var rr = Math.round(ar + (br - ar) * r), rg = Math.round(ag + (bgc - ag) * r), rb = Math.round(ab + (bb - ab) * r);
    return '#' + ((1 << 24) + (rr << 16) + (rg << 8) + rb).toString(16).slice(1);
  }

  function applyAccent(v) {
    if (!v) return;
    root.style.setProperty('--vermilion', v);
    root.style.setProperty('--vermilion-dark', mix(v, '#000000', 0.18));
  }
  function applyBg(v) {
    if (!v) return;
    root.style.setProperty('--paper', v);
    root.style.setProperty('--card', mix(v, '#ffffff', 0.12));
  }
  function setTheme(t) {
    if (t === 'system') t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    root.setAttribute('data-theme', t);
  }

  // 初始化：选中当前主题、取色器回显已存自定义值
  var cur = localStorage.getItem(KEY_T) || 'light';
  var radios = opts.querySelectorAll('input[type=radio]');
  for (var i = 0; i < radios.length; i++) if (radios[i].value === cur) radios[i].checked = true;
  var ca = localStorage.getItem(KEY_A); if (ca) accent.value = ca;
  var cb = localStorage.getItem(KEY_B); if (cb) bg.value = cb;

  // 切换预设主题
  opts.addEventListener('change', function (e) {
    if (e.target.name !== 'gtheme') return;
    localStorage.setItem(KEY_T, e.target.value);
    setTheme(e.target.value);
  });

  // 自定义主色
  accent.addEventListener('input', function () {
    localStorage.setItem(KEY_A, accent.value);
    applyAccent(accent.value);
  });
  // 自定义背景色
  bg.addEventListener('input', function () {
    localStorage.setItem(KEY_B, bg.value);
    applyBg(bg.value);
  });
  // 重置自定义（回退到所选主题的默认变量）
  reset.addEventListener('click', function () {
    localStorage.removeItem(KEY_A);
    localStorage.removeItem(KEY_B);
    root.style.removeProperty('--vermilion');
    root.style.removeProperty('--vermilion-dark');
    root.style.removeProperty('--paper');
    root.style.removeProperty('--card');
    accent.value = '#9d2933';
    bg.value = '#f7f4ec';
  });

  // 面板开合
  toggle.addEventListener('click', function (e) {
    e.stopPropagation();
    panel.hidden = !panel.hidden;
  });
  document.addEventListener('click', function (e) {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== toggle) panel.hidden = true;
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') panel.hidden = true;
  });

  // 跟随系统：系统主题变化时实时响应
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  function onSys() { if ((localStorage.getItem(KEY_T) || 'light') === 'system') setTheme('system'); }
  if (mq.addEventListener) mq.addEventListener('change', onSys);
  else if (mq.addListener) mq.addListener(onSys);
})();
