<!doctype html><html><head><meta charset='utf-8'><style>
:root{
  --bg:#f8fafc; --panel:#ffffff; --panel2:#f1f5f9; --panel3:#e2e8f0;
  --line:#e2e8f0; --line-hover:#cbd5e1;
  --fg:#0f172a; --dim:#64748b; --dim-light:#94a3b8;
  --accent:#2563eb; --accent-hover:#1d4ed8; --accent-soft:rgba(37,99,235,.08);
  --accent2:#16a34a; --accent2-soft:rgba(22,163,74,.1);
  --warn:#d97706; --warn-soft:rgba(217,119,6,.1);
  --think:#7c3aed; --think-soft:rgba(124,58,237,.08);
  --bad:#dc2626; --bad-soft:rgba(220,38,38,.08);
  --shadow-sm:0 1px 2px 0 rgba(15,23,42,.05);
  --shadow:0 1px 3px 0 rgba(15,23,42,.06),0 1px 2px -1px rgba(15,23,42,.04);
  --shadow-md:0 4px 6px -2px rgba(15,23,42,.06),0 2px 4px -2px rgba(15,23,42,.04);
  --header-bg:rgba(255,255,255,.94);
  /* 页面左右留白：header 与 main 共用同一个值，窄屏收窄、宽屏封顶 28px，
     免得主区域两侧堆出一大片用不上的空白。 */
  --page-pad:clamp(14px,1.4vw,28px);
  color-scheme:light;
}
[data-theme="dark"]{
  --bg:#0b0f19; --panel:#111827; --panel2:#1e293b; --panel3:#334155;
  --line:#1f293d; --line-hover:#334155;
  --fg:#f1f5f9; --dim:#94a3b8; --dim-light:#64748b;
  --accent:#3b82f6; --accent-hover:#60a5fa; --accent-soft:rgba(59,130,246,.15);
  --accent2:#22c55e; --accent2-soft:rgba(34,197,94,.15);
  --warn:#f59e0b; --warn-soft:rgba(245,158,11,.15);
  --think:#c084fc; --think-soft:rgba(192,132,252,.15);
  --bad:#f87171; --bad-soft:rgba(248,113,113,.15);
  --shadow-sm:0 1px 2px 0 rgba(0,0,0,.35);
  --shadow:0 1px 3px 0 rgba(0,0,0,.45),0 1px 2px -1px rgba(0,0,0,.35);
  --shadow-md:0 4px 6px -2px rgba(0,0,0,.55),0 2px 4px -2px rgba(0,0,0,.45);
  --header-bg:rgba(11,15,25,.92);
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased}
header{padding:16px var(--page-pad);border-bottom:1px solid var(--line);display:flex;
  align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  position:sticky;top:0;background:var(--header-bg);backdrop-filter:blur(10px);z-index:10;box-shadow:var(--shadow-sm)}
h1{margin:0;font-size:17px;font-weight:700;letter-spacing:-.2px;color:var(--fg)}
h1 span{color:var(--dim);font-weight:400;font-size:13px;margin-left:8px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent2);
  margin-right:7px;vertical-align:middle;box-shadow:0 0 0 2px rgba(22,163,74,.2)}
.dot.err{background:var(--bad);box-shadow:0 0 0 2px rgba(220,38,38,.2)}
.meta{color:var(--dim);font-size:12px;text-align:right;line-height:1.6}
.meta b{color:var(--fg);font-weight:600}
main{padding:20px var(--page-pad) 60px;max-width:2000px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;box-shadow:var(--shadow);min-width:0}
.card .k{color:var(--dim);font-size:12px;margin-bottom:6px;font-weight:500}
.card .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.5px;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .s{color:var(--dim);font-size:11px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card.think .v{color:var(--think)}
.card.accent .v{color:var(--accent)}
.card.accent2 .v{color:var(--accent2)}
.card.err .v{color:var(--bad)}
#cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:20px}
#cards .card{padding:14px 18px;min-width:0;border-radius:12px;background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);display:flex;flex-direction:column;justify-content:space-between;min-height:92px}
#cards .card .k{font-size:12px;color:var(--dim);margin-bottom:8px;font-weight:600;letter-spacing:.2px}
#cards .card .v{font-size:22px;font-weight:700;letter-spacing:-.3px;color:var(--fg);display:flex;align-items:baseline}
#cards .card .v-split{display:flex;flex-direction:column;gap:5px;width:100%}
#cards .card .v-row{display:flex;align-items:baseline;justify-content:space-between;font-size:13px;line-height:1.2}
#cards .card .v-label{font-size:11px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.4px}
#cards .card .v-num{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--fg)}
#cards .card .v-unit{font-size:11px;font-weight:400;color:var(--dim);margin-left:3px}
section{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin-bottom:20px;box-shadow:var(--shadow)}
section h2{margin:0 0 14px;font-size:13px;font-weight:700;color:var(--dim);
  text-transform:uppercase;letter-spacing:.6px}
section h2 em{color:var(--fg);font-style:normal;text-transform:none;letter-spacing:0;margin-left:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:right;padding:9px 12px;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums;vertical-align:middle}
th{color:var(--dim);font-weight:600;font-size:12px;white-space:nowrap;background:var(--panel2)}
/* 积分扣减历史：外层容器自己纵向滚动，表头不钉住的话滑到下面就看不出哪列是哪列。
   表头本来就有 --panel2 底色（不透明），加 sticky 即可盖住滚上来的行。 */
#creditHistoryTable thead th{position:sticky;top:0;z-index:2;
  box-shadow:inset 0 -1px 0 var(--line)}
th:first-child{border-top-left-radius:8px;border-bottom-left-radius:8px}
th:last-child{border-top-right-radius:8px;border-bottom-right-radius:8px}
th:first-child,td:first-child{text-align:left}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--panel2)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
/* 输入 / 输出 / 思考：三个数字应该在一行内读完，不拆行 */
.triple{white-space:nowrap}
.bar-fill{height:6px;border-radius:3px;background:var(--accent);min-width:2px;display:inline-block;vertical-align:middle}
.bar-fill.think{background:var(--think)}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%;border-radius:8px}
.table-wrap table{min-width:720px}
#recent table th, #recent table td{text-align:center}
#recent table th:first-child, #recent table td:first-child{text-align:center}
#recent table td.mono{font-variant-numeric:tabular-nums}
/* 限额表：一列一个作用域，输入框右对齐，同列数字才对得齐 */
.limit-input{width:100%;max-width:200px;background:var(--panel2);border:1px solid var(--line);
  border-radius:8px;padding:8px 12px;color:var(--fg);font:inherit;text-align:right}
.limit-input::placeholder{color:var(--dim);opacity:.75}
@media (min-width: 0px){
  header{padding:12px 16px}
  main{padding:16px 12px 60px}
  section{padding:14px 14px;border-radius:12px}
  #cards{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
  #cards .card{padding:10px 12px}
  #cards .card .v{font-size:18px}
  .toolbar{gap:6px}
  .toolbar button{padding:5px 10px;font-size:11px}
}
/* 账号区折叠。chevron 的指向跟着 aria-expanded 走，正文用
   grid-template-rows 收放：0fr 本身就是收起，所以没有动画也正确，也不必给
   列表猜一个 max-height（账号一多就会被截断）。hoverTip 是挂在 body 上的
   全局单例，不受这里的 overflow 影响。 */
.disclosure{display:inline-flex;align-items:center;gap:7px;background:transparent;
  border:none;padding:3px 7px;margin:-3px -7px;font:inherit;color:inherit;cursor:pointer;border-radius:8px}
/* 焦点态给一个柔和的胶囊高亮（淡蓝底 + 细描边），而不是贴着字画一圈硬描边。
   padding 与 margin 成对出现，聚焦时标题文字的位置不会动。 */
.disclosure:focus-visible{outline:none;background:var(--accent-soft);box-shadow:0 0 0 1.5px var(--accent)}
.disclosure-chevron{width:0;height:0;border-left:5px solid currentColor;
  border-top:4px solid transparent;border-bottom:4px solid transparent;
  transition:transform .18s ease;transform:rotate(90deg)}
.disclosure[aria-expanded="false"] .disclosure-chevron{transform:rotate(0deg)}
.collapse{display:grid;grid-template-rows:1fr;transition:grid-template-rows .18s ease}
.collapse.collapsed{grid-template-rows:0fr}
.collapse>.collapse-inner{min-height:0;overflow:hidden}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;
  background:var(--panel2);border:1px solid var(--line);color:var(--dim);white-space:nowrap;font-weight:600}
.badge.ok{color:#15803d;background:rgba(34,197,94,.14);border-color:rgba(34,197,94,.32)}
.badge.s{color:#1d4ed8;background:rgba(37,99,235,.1);border-color:rgba(37,99,235,.25)}
.badge.off{color:#64748b;background:#e2e8f0;border-color:#cbd5e1}
.badge.warn{color:#b45309;background:rgba(245,158,11,.14);border-color:rgba(245,158,11,.35)}
.badge.bad{color:#b91c1c;background:rgba(239,68,68,.14);border-color:rgba(239,68,68,.35)}
.badge.mini{padding:1px 6px;font-size:10px}
.cool-list{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.cool-pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:600;
  color:#b45309;background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.35);white-space:nowrap}
.empty{color:var(--dim);text-align:center;padding:28px 0;font-size:13px}
/* 价格悬停气泡：自绘，才能对齐单价并截图验收；pointer-events:none 让它不会
   抢走鼠标、把 hover 打断。 */
.cost-cell{cursor:help}
/* 价估算总开关关闭时，除开关本身外整块功能从界面上撤掉：价格列、KPI 卡片、
   设置页的取价子控件与未定价清单一并隐藏，只留下开关，方便随时再打开。 */
body.pricing-off .pricing-col{display:none}
body.pricing-off #kpiCostCard{display:none}
/* 胶囊式开关：原生 checkbox 管状态与键盘可达性，视觉交给 .switch-track。
   点一下即切换并立即保存，所以不再另配「保存」按钮。 */
.switch{position:relative;display:inline-flex;align-items:center;gap:8px;font-size:13px;
  min-height:40px;cursor:pointer;user-select:none}
.switch input{position:absolute;width:1px;height:1px;opacity:0;margin:0}
.switch-track{position:relative;flex:0 0 auto;width:38px;height:20px;border-radius:999px;
  background:var(--panel2);border:1px solid var(--line);
  transition:background .18s ease,border-color .18s ease}
.switch-track::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;
  border-radius:50%;background:var(--dim);transition:transform .18s ease,background .18s ease}
.switch input:checked+.switch-track{background:var(--accent2);border-color:var(--accent2)}
.switch input:checked+.switch-track::after{transform:translateX(18px);background:#fff}
.switch input:focus-visible+.switch-track{outline:2px solid var(--accent2);outline-offset:2px}
#costTip{position:fixed;z-index:80;display:none;max-width:min(480px,94vw);padding:10px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--fg);
  font-size:12px;line-height:1.7;box-shadow:0 14px 34px rgba(15,23,42,.28);pointer-events:none}
#costTip .ct-h{color:var(--dim);font-size:11px;letter-spacing:.02em}
#costTip .ct-line{margin-top:2px}
#costTip .ct-row{display:flex;gap:18px;justify-content:space-between;margin-top:2px}
#costTip .ct-k{color:var(--dim)}
#costTip .ct-v{font-variant-numeric:tabular-nums;white-space:nowrap}
#costTip .ct-note{color:var(--dim);font-size:11px;margin-top:4px}
#costTip .ct-sep{height:1px;background:var(--line);margin:7px 0}
.legend{display:flex;gap:16px;color:var(--dim);font-size:11px;margin-top:12px;flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
/* 工具栏按用途分组：组与组之间一条浅色竖线（窄屏换行时它跟着按钮走，不会掉队） */
.toolbar-sep{width:1px;align-self:stretch;min-height:20px;background:var(--line);margin:0 2px;border-radius:1px}
button{cursor:pointer;font:inherit;font-size:12px;font-weight:500;padding:6px 14px;border-radius:8px;
  border:1px solid var(--accent);background:var(--accent);color:#fff;box-shadow:var(--shadow-sm);transition:all .15s ease}
button:hover{background:var(--accent-hover);border-color:var(--accent-hover)}
button:disabled{opacity:.45;cursor:not-allowed}
button.sec{background:var(--panel);border-color:var(--line);color:var(--fg);box-shadow:var(--shadow-sm)}
button.sec:hover{background:var(--panel2);border-color:var(--line-hover)}
button.danger{border-color:rgba(220,38,38,.3);background:rgba(220,38,38,.06);color:var(--bad)}
button.danger:hover{background:var(--bad);color:#fff;border-color:var(--bad)}
button.mini{padding:3px 9px;font-size:11px}
.id-btn-group{display:inline-flex;gap:2px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px}
.id-btn{background:transparent;border:none;color:var(--dim);padding:2px 6px;border-radius:4px;font-size:11px;font-weight:500;cursor:pointer;transition:all .15s}
.id-btn:hover{color:var(--fg)}
.id-btn-label{color:var(--dim);font-size:11px;white-space:nowrap}
.id-btn.active{background:var(--accent);color:#fff;font-weight:600;box-shadow:var(--shadow-sm)}
.slot-select{background:var(--panel2);border:1px solid var(--line);border-radius:8px;
  padding:5px 8px;color:var(--fg);font:inherit;font-size:12px;max-width:140px}
.slot-input{width:100%;background:var(--panel2);border:1px solid var(--line);
  border-radius:8px;padding:6px 10px;color:var(--fg);font:inherit;font-size:13px}
.acct-actions-col{display:flex;flex-direction:column;gap:5px;align-items:center;justify-content:center}
.acct-actions-row{display:flex;gap:4px;justify-content:center}
.modal-mask{display:none;position:fixed;inset:0;background:rgba(15,23,42,.45);
  backdrop-filter:blur(4px);align-items:center;justify-content:center;padding:20px;z-index:100}
.modal-mask.show{display:flex}
.modal{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  width:min(620px,100%);max-height:88vh;overflow:auto;box-shadow:0 20px 25px -5px rgba(0,0,0,.1),0 8px 10px -6px rgba(0,0,0,.05)}
.modal-hd{display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px;border-bottom:1px solid var(--line)}
.modal-hd h2{margin:0;font-size:15px;font-weight:700;text-transform:none;letter-spacing:0;color:var(--fg)}
.modal-x{background:none;border:none;color:var(--dim);font-size:22px;line-height:1;padding:0 4px;cursor:pointer}
.modal-x:hover{color:var(--fg)}
.modal-bd{padding:18px 20px}
.modal-ft{padding:14px 20px;border-top:1px solid var(--line);display:flex;
  justify-content:flex-end;gap:8px}
.login-link{display:block;word-break:break-all;background:var(--panel2);
  border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:12px 0;
  color:var(--accent);text-decoration:none;font-size:12px}
.login-link:hover{border-color:var(--accent);background:var(--panel)}
.hint{color:var(--dim);font-size:12px;margin:8px 0}
.step{display:flex;gap:10px;align-items:flex-start;margin:10px 0}
.step .n{flex:0 0 20px;height:20px;border-radius:50%;background:var(--panel2);
  border:1px solid var(--line);color:var(--dim);font-size:11px;display:flex;
  align-items:center;justify-content:center}
.step.active .n{border-color:var(--accent);background:rgba(37,99,235,.1);color:var(--accent);font-weight:700}
.step.done .n{border-color:var(--accent2);background:rgba(22,163,74,.1);color:var(--accent2);font-weight:700}
.step .t{font-size:13px}
footer{color:var(--dim);font-size:12px;text-align:center;margin-top:28px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.realm-switch-group{display:inline-flex;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:3px;gap:3px}
.realm-pill{background:transparent;border:none;color:var(--dim);font-size:12px;padding:6px 16px;border-radius:8px;cursor:pointer;transition:all .15s}
.realm-pill:hover{color:var(--fg)}
.realm-pill.active{background:var(--accent);color:#fff;font-weight:600;box-shadow:var(--shadow-sm)}
.key-card{
  background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 20px;margin-bottom:12px;box-shadow:var(--shadow);
  transition:all .15s ease;
}
.key-card:hover{border-color:var(--line-hover);box-shadow:var(--shadow-md)}
.key-card.disabled{opacity:.75;background:var(--panel2)}
.key-card-main{
  display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
}
.key-action-btn{
  display:inline-flex;align-items:center;gap:5px;padding:5px 14px;border-radius:20px;
  font-size:12px;font-weight:500;cursor:pointer;border:1px solid var(--line);
  background:var(--panel);color:var(--fg);transition:all .15s ease;box-shadow:var(--shadow-sm);
}
.key-action-btn:hover{background:var(--panel2);border-color:var(--line-hover)}
.key-action-btn.danger{
  color:#dc2626;border-color:rgba(220,38,38,.28);background:rgba(220,38,38,.03);
}
.key-action-btn.danger:hover{
  background:#dc2626;color:#ffffff;border-color:#dc2626;
}
.realm-badge-intl{color:#0369a1;background:rgba(2,132,199,.12);border:1px solid rgba(2,132,199,.3);padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600}
.realm-badge-cn{color:#b91c1c;background:rgba(220,38,38,.12);border:1px solid rgba(220,38,38,.3);padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600}
.badge-effort{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;line-height:1.4;white-space:nowrap;margin:1px 2px;background:rgba(124,58,237,.12);color:var(--think);border:1px solid rgba(124,58,237,.3);font-weight:600}
.realm-filter{display:inline-flex;gap:6px;margin-left:8px}
.realm-filter button{background:var(--panel2);border:1px solid var(--line);color:var(--dim);padding:3px 9px;font-size:11px}
.realm-filter button.active{border-color:var(--accent);color:var(--accent);background:var(--panel)}

.realm-card{
  background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 18px;box-shadow:var(--shadow);cursor:pointer;transition:all .15s ease;
  position:relative;display:flex;flex-direction:column;justify-content:space-between;min-height:104px;
}
.realm-card:hover{border-color:var(--line-hover);transform:translateY(-1px);box-shadow:var(--shadow-md)}
.realm-card.active{
  border-color:var(--accent);background:var(--panel);
  box-shadow:0 0 0 1px var(--accent), var(--shadow-md);
}
.realm-card.active#tabCn{
  border-color:#ef4444;box-shadow:0 0 0 1px #ef4444, var(--shadow-md);
}
.realm-card.gateway-ctrl{
  background:var(--panel2);cursor:default;border-color:var(--line);
}
.realm-card.gateway-ctrl:hover{transform:none;border-color:var(--line);box-shadow:var(--shadow)}
.toggle-realm-btn{
  background:var(--panel);border:1px solid var(--accent);color:var(--accent);
  padding:8px 18px;font-size:13px;font-weight:600;border-radius:8px;box-shadow:var(--shadow-sm);cursor:pointer;
  transition:all .15s ease;
}
.toggle-realm-btn:hover{background:var(--panel2);box-shadow:var(--shadow-md)}
.realm-endpoint-info{font-size:12px;color:var(--dim)}

.main-nav{display:inline-flex;gap:4px;background:var(--panel2);padding:4px;border-radius:10px;border:1px solid var(--line)}
.main-nav-btn{background:transparent;border:1px solid transparent;color:var(--dim);padding:6px 14px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:all .15s ease}
.main-nav-btn:hover{color:var(--fg);background:var(--panel)}
.main-nav-btn.active{background:var(--panel);color:var(--fg);border-color:var(--line);box-shadow:var(--shadow-sm);font-weight:600}
/* 项目仓库入口：与顶部导航同行，但不作为一个 Tab 标签。 */
.gh-link{display:inline-flex;align-items:center;justify-content:center;
  width:34px;height:32px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel);color:var(--dim);box-shadow:var(--shadow-sm);
  transition:all .15s ease}
.gh-link:hover{color:var(--fg);border-color:var(--line-hover);
  background:var(--panel2);text-decoration:none;box-shadow:var(--shadow-md)}
.gh-link svg{width:17px;height:17px;display:block;fill:currentColor}

/* 顶部右侧区域与主题切换组件 (黑白单色、极简线条Outline、符合规范) */
.header-right{display:flex;align-items:center;gap:10px}
.theme-dropdown-wrap{position:relative;display:inline-flex}
.theme-btn{
  display:inline-flex;align-items:center;justify-content:center;
  width:34px;height:32px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel);color:var(--dim);box-shadow:var(--shadow-sm);
  cursor:pointer;padding:0;transition:all .15s ease;
}
.theme-btn:hover{
  color:var(--fg);border-color:var(--line-hover);
  background:var(--panel2);box-shadow:var(--shadow-md);
}
.theme-btn-icon{width:16px;height:16px;display:inline-flex;align-items:center;justify-content:center}
.theme-btn-icon svg{width:16px;height:16px;display:block}
.theme-dropdown{
  display:none;position:absolute;top:calc(100% + 6px);right:0;
  min-width:130px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;padding:4px;box-shadow:var(--shadow-md);
  z-index:100;backdrop-filter:blur(8px);
}
.theme-dropdown.open{display:block;animation:themePop .12s cubic-bezier(0,0,.2,1)}
@keyframes themePop{from{opacity:0;transform:scale(.96) translateY(-4px)}to{opacity:1;transform:scale(1) translateY(0)}}
.theme-option{
  width:100%;display:flex;align-items:center;gap:8px;padding:7px 10px;
  border-radius:6px;border:none;background:transparent;color:var(--fg);
  font-size:12px;cursor:pointer;text-align:left;transition:background .12s ease;
  box-shadow:none;
}
.theme-option:hover{background:var(--panel2)}
.theme-opt-icon{width:14px;height:14px;flex-shrink:0;color:var(--dim)}
.theme-option:hover .theme-opt-icon{color:var(--fg)}
.theme-opt-text{flex:1;font-weight:500}
.theme-opt-check{width:13px;height:13px;flex-shrink:0;opacity:0;color:var(--accent)}
.theme-option.active .theme-opt-check{opacity:1}
.theme-option.active{font-weight:600;color:var(--accent)}
.theme-option.active .theme-opt-icon{color:var(--accent)}
.lang-btn{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:34px;height:32px;padding:0 8px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel);color:var(--dim);box-shadow:var(--shadow-sm);
  cursor:pointer;font:inherit;font-size:12px;font-weight:700;transition:all .15s ease;
}
.lang-btn:hover{
  color:var(--fg);border-color:var(--line-hover);
  background:var(--panel2);box-shadow:var(--shadow-md);
}
@media (min-width: 0px){
  .lang-btn{min-width:36px;height:36px;padding:0 6px;font-size:12px}
}

[data-theme="dark"] .badge.ok{color:#4ade80;background:rgba(34,197,94,.16);border-color:rgba(34,197,94,.32)}
[data-theme="dark"] .badge.s{color:#60a5fa;background:rgba(59,130,246,.16);border-color:rgba(59,130,246,.32)}
[data-theme="dark"] .badge.off{color:#94a3b8;background:rgba(148,163,184,.14);border-color:rgba(148,163,184,.22)}
[data-theme="dark"] .badge.warn{color:#fbbf24;background:rgba(245,158,11,.16);border-color:rgba(245,158,11,.35)}
[data-theme="dark"] .badge.bad{color:#f87171;background:rgba(248,113,113,.16);border-color:rgba(248,113,113,.35)}
[data-theme="dark"] .cool-pill{color:#fbbf24;background:rgba(245,158,11,.18);border-color:rgba(245,158,11,.38)}
[data-theme="dark"] .realm-badge-intl{color:#38bdf8;background:rgba(2,132,199,.2);border-color:rgba(2,132,199,.4)}
[data-theme="dark"] .realm-badge-cn{color:#f87171;background:rgba(220,38,38,.2);border-color:rgba(220,38,38,.4)}
[data-theme="dark"] .modal-mask{background:rgba(0,0,0,.65)}
/* The page sections are toggled by a class so the inline head script can
   choose one before the body is parsed, avoiding a flash of the wrong
   page on every reload. */
.main-page{display:none}
.main-page.active{display:block}
/* 页面级两栏：左侧区块导航由 initPageNav() 依据页面内的 section 现场生成，
   这里的样式只描述外观，既不预设任何页面，也不预设任何区块。给页面加
   .page-nav-on 即可启用，区块不足两项的页面不加这个类，保持单栏。 */
.main-page.page-nav-on.active{display:grid;grid-template-columns:196px minmax(0,1fr);gap:20px;align-items:start}
.main-page.page-nav-on > *{grid-column:2;min-width:0}
/* 内容包在 .page-nav-body 里，grid 就只有两项，1 / -1 才真的跨满整个内容区
   （否则它只跨第 1 行，首行被撑成侧栏高度）；区块间距也仍只由 section 自己
   的 margin 决定，不会被行间距再叠一次。 */
.main-page.page-nav-on > .page-sidebar{grid-column:1;grid-row:1 / -1;position:sticky;
  top:var(--page-nav-top,84px);z-index:6;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:10px;box-shadow:var(--shadow);
  max-height:calc(100vh - var(--page-nav-top,84px) - 20px);overflow:auto}
.page-sidebar-title{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;
  letter-spacing:.6px;padding:6px 10px 8px}
.page-nav{display:flex;flex-direction:column;gap:2px}
.page-nav-item{appearance:none;background:transparent;border:1px solid transparent;color:var(--dim);
  text-align:left;padding:8px 10px;border-radius:8px;font:inherit;font-size:13px;line-height:1.35;
  cursor:pointer;transition:all .15s ease;overflow-wrap:anywhere}
.page-nav-item:hover{color:var(--fg);background:var(--panel2)}
.page-nav-item.active{color:var(--fg);background:var(--panel2);border-color:var(--line);font-weight:600}
/* 回到顶部：排在区块清单上方，所以留出与清单的间距 */
button.page-nav-top{display:flex;align-items:center;justify-content:center;gap:6px;width:100%;
  margin-bottom:8px;padding:7px 10px;border-radius:8px;font-size:12px;font-weight:600;
  background:var(--panel2);border:1px solid var(--line);color:var(--fg);box-shadow:none;
  transition:all .15s ease}
button.page-nav-top:hover{background:var(--panel2);border-color:var(--accent);color:var(--accent)}
.page-sidebar-head{display:flex;align-items:center;justify-content:space-between;gap:6px}
.page-sidebar-toggle{appearance:none;flex:0 0 auto;width:22px;height:22px;padding:0;
  display:inline-flex;align-items:center;justify-content:center;border-radius:6px;
  border:1px solid var(--line);background:var(--panel2);color:var(--dim);
  font:inherit;font-size:12px;line-height:1;cursor:pointer;transition:all .15s ease}
.page-sidebar-toggle:hover{color:var(--fg);border-color:var(--line-hover)}
/* 收起侧栏：整列压成一条细轨，只留展开按钮，把宽度让给内容区。窄屏下导航
   本来就是一条横栏，没有可收的余地，所以这套样式只在宽屏生效。 */
@media (min-width:861px){
  .main-page.page-nav-on.page-nav-collapsed.active{grid-template-columns:44px minmax(0,1fr);gap:12px}
  .main-page.page-nav-on.page-nav-collapsed > .page-sidebar{padding:6px 4px;overflow:hidden}
  .main-page.page-nav-on.page-nav-collapsed .page-sidebar-title,
  .main-page.page-nav-on.page-nav-collapsed .page-nav,
  .main-page.page-nav-on.page-nav-collapsed button.page-nav-top{display:none}
  .main-page.page-nav-on.page-nav-collapsed .page-sidebar-head{justify-content:center;padding:0}
}
.main-page.page-nav-on section{scroll-margin-top:var(--page-nav-top,84px)}
/* 点击导航后短暂描边，明确「跳到这里了」 */
.main-page.page-nav-on section.page-nav-flash{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:860px){
  .main-page.page-nav-on.active{grid-template-columns:minmax(0,1fr);gap:14px}
  .main-page.page-nav-on > *{grid-column:1}
  .main-page.page-nav-on > .page-sidebar{grid-row:auto;max-height:none;overflow:visible;padding:8px;
    border-radius:12px;background:var(--header-bg);backdrop-filter:blur(10px);
    display:flex;align-items:center;gap:8px}
  .page-sidebar-title{display:none}
  /* 窄屏导航是横向胶囊行，收不起来，连收起按钮一起藏掉 */
  .page-sidebar-head{display:none}
  .page-nav{flex:1 1 auto;min-width:0;flex-direction:row;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px;
    scrollbar-width:thin}
  .page-nav-item{white-space:nowrap;padding:7px 12px;border-radius:999px;
    background:var(--panel2);border-color:var(--line)}
  /* 窄屏下导航是横向滚动的胶囊行，回到顶部钉在左端不跟着滚 */
  button.page-nav-top{width:auto;flex:0 0 auto;margin-bottom:0;padding:7px 12px;border-radius:999px;
    white-space:nowrap}
}
.range-btn{background:transparent;border:none;color:var(--dim);padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s ease}
.range-btn:hover{color:var(--fg)}
.range-btn.active{background:var(--accent);color:#fff;font-weight:600;box-shadow:var(--shadow-sm)}
#analyticsKpiCards{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:8px}
#analyticsKpiCards .card{padding:12px 16px;min-width:0;overflow:hidden;border-radius:12px;background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow)}
#analyticsKpiCards .card .v{font-size:19px;font-weight:700;white-space:nowrap}
#analyticsKpiCards .card .k{font-size:11px;white-space:nowrap;margin-bottom:3px;font-weight:600;color:var(--dim)}
#analyticsKpiCards .card .s{font-size:10px;white-space:normal;line-height:1.35;margin-top:2px;color:var(--dim)}
.model-pill{display:inline-flex;align-items:center;gap:4px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:11px;margin:2px 4px 2px 0;white-space:nowrap}
/* 归属表表头里的行开关，直接复用设置页的 .switch 胶囊样式，只是表头比
   设置页紧凑，把 40px 的最小高度收掉。 */
.key-row-switch{min-height:0}
.log-line{display:flex;align-items:flex-start;gap:8px;padding:3px 6px;border-radius:4px;font-family:Consolas,Monaco,'Courier New',monospace;font-size:12px;line-height:1.55;transition:background .1s}
.log-line:hover{background:rgba(255,255,255,.05)}
.log-ts{color:#64748b;font-variant-numeric:tabular-nums;flex-shrink:0;user-select:none}
.log-lvl{font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px;flex-shrink:0;text-align:center;min-width:46px;user-select:none}
.log-lvl.lvl-INFO{background:rgba(37,99,235,.2);color:#60a5fa}
.log-lvl.lvl-WARN{background:rgba(217,119,6,.2);color:#fbbf24}
.log-lvl.lvl-ERROR{background:rgba(220,38,38,.25);color:#f87171}
.log-lvl.lvl-DEBUG{background:rgba(148,163,184,.2);color:#94a3b8}
.log-tag{font-size:11px;font-weight:600;padding:1px 5px;border-radius:3px;flex-shrink:0;background:rgba(148,163,184,.12);color:#94a3b8;user-select:none}
.log-tag.tag-chat{background:rgba(124,58,237,.18);color:#c084fc}
.log-tag.tag-scheduler{background:rgba(22,163,74,.18);color:#4ade80}
.log-tag.tag-tasks{background:rgba(234,179,8,.18);color:#facc15}
.log-tag.tag-accounts{background:rgba(14,165,233,.18);color:#38bdf8}
.log-tag.tag-auth{background:rgba(244,63,94,.18);color:#fb7185}
.log-tag.tag-system{background:rgba(100,116,139,.18);color:#94a3b8}
.log-msg{color:#cbd5e1;flex:1;word-break:break-all;white-space:pre-wrap}
.log-empty{padding:48px 24px;text-align:center;color:#64748b;font-size:13px;font-family:inherit}
/* ===== Phone: ≤640px ===== */
@media (min-width: 0px){
  header{padding:10px 12px;gap:8px}
  .header-left{width:auto;flex:1;gap:8px;min-width:0}
  .header-right{display:flex;align-items:center;gap:6px;order:2}
  h1{font-size:15px;flex:1;min-width:0}
  h1 span{font-size:11px;margin-left:6px}
  .gh-link{width:36px;height:36px;flex-shrink:0}
  .theme-btn{width:36px;height:36px}
  /* 窄屏下主 Tab 一排摆不下就横向滚动，而不是把行内容顶出导航条：5 个 Tab 的
     min-content 和已经超过这段留给导航的宽度（右侧按钮组占了 84px），继续用
     flex:1 平分只会把按钮压到 min-content 并溢出（issue #246 实测 320px 溢出
     59px、414px 起就不等宽）。做法与 .page-nav 在 ≤860px 时一致：按钮保持
     可读宽度，摆不下就滚动；放得下时仍然平分整行。 */
  .main-nav{display:flex;width:100%;gap:2px;padding:3px;order:3;overflow-x:auto;
    -webkit-overflow-scrolling:touch;scrollbar-width:thin}
  .main-nav-btn{flex:1 0 auto;justify-content:center;padding:8px 2px;font-size:12px;min-height:36px;white-space:nowrap}
  .meta{width:100%;text-align:left;font-size:11px;line-height:1.5;order:4}
  .meta .meta-secondary{display:none}
  /* Table → card */
  .table-wrap{overflow:visible}
  table.data-cards{min-width:0!important;display:block}
  table.data-cards thead{display:none}
  table.data-cards tbody{display:block}
  table.data-cards tr{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));
    gap:5px 8px;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;padding:12px;margin-bottom:10px;box-shadow:var(--shadow-sm)}
  table.data-cards td{display:flex;align-items:baseline;justify-content:space-between;
    gap:12px;grid-column:span 6;border:none;padding:1px 0;text-align:left!important;
    font-variant-numeric:tabular-nums;min-width:0;overflow-wrap:anywhere;word-break:break-word}
  table.data-cards td::before{content:attr(data-label);color:var(--dim);font-size:11px;
    font-weight:600;flex-shrink:0}
  table.data-cards td:not([data-label])::before{content:none}
  /* 限额表：护栏名与说明占整块，三个作用域各一行 */
  table.limits-cards td.limit-name{display:block;padding-bottom:6px}
  table.data-cards td[colspan]{grid-column:span 6;justify-content:center;text-align:center!important}
  table.data-cards td[colspan]::before{content:none}
  /* Account card: grouped layout */
  table.account-cards td:nth-child(1){order:1;grid-column:span 3;justify-content:flex-start}
  table.account-cards td:nth-child(1)::before,
  table.account-cards td:nth-child(2)::before,
  table.account-cards td:nth-child(3)::before{content:none}
  table.account-cards td:nth-child(2){order:3;grid-column:span 6;flex-direction:column;align-items:flex-start;gap:2px}
  table.account-cards td:nth-child(3){order:2;grid-column:span 3;justify-content:flex-end}
  table.account-cards td:nth-child(4){order:4;grid-column:span 6;flex-direction:column;align-items:stretch;gap:4px}
  table.account-cards td:nth-child(4)::before{font-size:10px}
  table.account-cards td:nth-child(5){order:5;grid-column:span 6}
  table.account-cards td:nth-child(6),
  table.account-cards td:nth-child(7),
  table.account-cards td:nth-child(8){order:6;grid-column:span 2;flex-direction:column-reverse;
    align-items:center;justify-content:center;gap:0;padding:4px 0;
    background:var(--panel2);border-radius:8px}
  table.account-cards td:nth-child(6)::before,
  table.account-cards td:nth-child(7)::before,
  table.account-cards td:nth-child(8)::before{font-size:10px}
  table.account-cards td.acct-actions{order:7;grid-column:span 6;justify-content:flex-start}
  table.account-cards td.acct-actions::before{content:none}
  table.account-cards .acct-actions-col{flex-direction:row;flex-wrap:wrap;align-items:flex-start;
    justify-content:flex-start;gap:6px}
  table.account-cards .acct-actions-row{flex-wrap:wrap;gap:6px}
  table.account-cards .acct-actions button.mini{min-height:32px;padding:6px 12px}
  table.account-cards .slot-select{max-width:none;width:100%;min-height:40px}
  /* Forms stack */
  #pageSettings section > div[style*="display:flex"]{flex-wrap:wrap}
  #pageSettings input:not([type=checkbox]), #pageSettings select{min-height:40px;font-size:13px}
  #pageSettings .slot-input{font-size:13px}
  table.data-cards td[data-label="启用"]{justify-content:space-between}
  table.data-cards td[data-label="启用"] input[type=checkbox]{width:20px;height:20px}
  /* Logs */
  #logTerminalBody{height:60vh!important}
  #pageLogs .toolbar{display:grid;grid-template-columns:1fr 1fr;gap:6px}
  #pageLogs .toolbar button{width:100%;min-height:34px}
  #pageLogs > div > div[style*="display:flex"]{flex-wrap:wrap}
  .log-line{flex-wrap:wrap;gap:4px}
  .log-msg{min-width:0;flex-basis:100%}
  /* Analytics KPI cards: wrap into a 2-column grid instead of one squeezed row */
  #analyticsKpiCards{grid-auto-flow:row;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  #analyticsKpiCards .card{padding:10px 12px}
  #analyticsKpiCards .card .k{white-space:normal}
  #analyticsKpiCards .card .v{font-size:16px}
  #analyticsKpiCards .card .s{white-space:normal;overflow:visible;text-overflow:clip}
  #analyticsKpiCards .card:last-child:nth-child(odd){grid-column:span 2}
  /* Dialogs */
  .modal-mask{padding:10px;align-items:flex-start}
  .modal{width:100%;max-height:94vh;border-radius:12px;margin-top:6px}
  .modal-hd{padding:12px 14px}
  .modal-bd{padding:14px}
  .modal-ft{padding:12px 14px;flex-wrap:wrap}
  .modal-ft button{flex:1;min-height:38px}
  .modal table td, .modal table th{padding:7px 8px}
}
/* ===== Small phone: ≤400px ===== */
@media (min-width: 0px){
  h1{font-size:14px}
  /* 小屏再挤一点：5 个 Tab 在 375px（iPhone SE/mini 一档）正好塞进一行 */
  .main-nav{gap:1px;padding:2px}
  .main-nav-btn{font-size:11px;padding:7px 2px}
  #cards{grid-template-columns:1fr 1fr;gap:6px}
  #cards .card .v{font-size:16px}
  table.data-cards tr{padding:10px}
  .log-ts{font-size:11px}
}
</style></head><body><div style='width:375px'><header>
  <div class="header-left" style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
    <h1><span class="dot" id="statusDot"></span>WorkBuddy 网关</h1>
    <nav class="main-nav">
      <button class="main-nav-btn active" id="btnNavGateway" onclick="switchMainTab('gateway')">
        网关与账号
      </button>
      <button class="main-nav-btn" id="btnNavAnalytics" onclick="switchMainTab('analytics')">
        数据看板
      </button>
      <button class="main-nav-btn" id="btnNavSettings" onclick="switchMainTab('settings')">
        设置
      </button>
      <button class="main-nav-btn" id="btnNavLogs" onclick="switchMainTab('logs')">
        运行日志
      </button>
    </nav>
    <a class="gh-link" href="https://github.com/ardeyouxipianyi/workbuddy2api-hub" target="_blank" rel="noopener noreferrer"
       title="查看 GitHub 项目仓库" aria-label="GitHub 项目仓库">
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>
      </svg>
    </a>
  </div>
  <div class="header-right">
    <button type="button" class="lang-btn" id="langToggleBtn" onclick="toggleLang(event)" data-no-i18n title="切换语言 (简体中文 / 正體中文 / English)" aria-label="切换语言">
      <span id="langToggleLabel">EN</span>
    </button>
    <div class="meta" id="meta"></div>
    <div class="theme-dropdown-wrap" id="themeDropdownWrap">
      <button type="button" class="theme-btn" id="themeToggleBtn" onclick="toggleThemeMenu(event)" title="颜色主题" aria-label="切换颜色主题" aria-haspopup="true" aria-expanded="false">
        <span id="themeToggleIcon" class="theme-btn-icon"></span>
      </button>
      <div class="theme-dropdown" id="themeDropdown" role="menu" aria-label="选择颜色主题">
        <button type="button" class="theme-option" id="themeOptLight" onclick="selectTheme('light', event)" role="menuitem">
          <svg class="theme-opt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4"></circle>
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path>
          </svg>
          <span class="theme-opt-text">浅色</span>
          <svg class="theme-opt-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
        </button>
        <button type="button" class="theme-option" id="themeOptDark" onclick="selectTheme('dark', event)" role="menuitem">
          <svg class="theme-opt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
          </svg>
          <span class="theme-opt-text">深色</span>
          <svg class="theme-opt-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
        </button>
        <button type="button" class="theme-option" id="themeOptSystem" onclick="selectTheme('system', event)" role="menuitem">
          <svg class="theme-opt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
          <span class="theme-opt-text">跟随系统</span>
          <svg class="theme-opt-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
        </button>
      </div>
    </div>
  </div>
</header></div><pre id='measure'>pending</pre><script>window.addEventListener('load', function(){var nav=document.querySelector('.main-nav');var btns=Array.from(document.querySelectorAll('.main-nav-btn'));var r=nav.getBoundingClientRect();var out={count:btns.length,innerW:window.innerWidth,widths:btns.map(function(b){return Math.round(b.getBoundingClientRect().width);}),navW:Math.round(r.width),scrollW:Math.round(nav.scrollWidth),clientW:Math.round(nav.clientWidth),overflow:Math.round(nav.scrollWidth-nav.clientWidth),headerW:Math.round(document.querySelector('header').getBoundingClientRect().width)};var hl=document.querySelector('.header-left');var hr=document.querySelector('.header-right');var h1=document.querySelector('header h1');var cs=getComputedStyle(nav);out.hlW=hl?Math.round(hl.getBoundingClientRect().width):null;out.hrW=hr?Math.round(hr.getBoundingClientRect().width):null;out.h1W=h1?Math.round(h1.getBoundingClientRect().width):null;out.navWidth=cs.width;out.navBasis=cs.flexBasis;out.navMin=cs.minWidth;out.navOrder=cs.order;document.getElementById('measure').textContent=JSON.stringify(out);});</script></body></html>