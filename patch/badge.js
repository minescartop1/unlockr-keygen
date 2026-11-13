(function () {
  if (document.getElementById('skCrackBadge')) return;
  var s = document.createElement('style');
  s.textContent = [
    '#skCrackBadge{position:fixed;left:0;right:0;bottom:0;z-index:2147483647;',
    'display:flex;justify-content:center;pointer-events:none;',
    'padding:8px 0 10px;margin:0;text-align:center;',
    'font:600 13px/1.35 system-ui,-apple-system,Roboto,sans-serif}',
    '#skCrackBadge span{display:block;white-space:nowrap;',
    'background-image:linear-gradient(90deg,#ff0040,#ff9f1c,#ffe600,#38e07b,#00d2ff,#4b5bff,#c04bff,#ff0040);',
    'background-size:300% 100%;-webkit-background-clip:text;background-clip:text;',
    'color:transparent;-webkit-text-fill-color:transparent;',
    'animation:skCrackFlow 4s linear infinite;transform:translateZ(0)}',
    '@keyframes skCrackFlow{from{background-position:0% 0}to{background-position:300% 0}}',
    '@media (prefers-reduced-motion:reduce){#skCrackBadge span{animation:none;background-position:50% 0}}'
  ].join('');
  (document.head || document.documentElement).appendChild(s);
  var b = document.createElement('div');
  b.id = 'skCrackBadge';
  var t = document.createElement('span');
  t.innerHTML = 'Crack by<br>@skidlarper333 on TikTok';
  b.appendChild(t);
  (document.body || document.documentElement).appendChild(b);
})();
