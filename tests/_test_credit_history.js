/* 积分扣减历史面板的两处缺陷：

   ① 表头不固定。外层容器自带 max-height + 纵向滚动，表头跟着一起滚走，
      滑到下面就看不出哪一列是哪一列。修法是给 thead 里的 th 加 sticky。
   ② 账号列只显示 uid 前 8 位。昵称来自 /accounts（与 /usage/timeseries 并行的
      另一条请求），所以晚到时要先用 uid 兜底、等账号到位再补画一次；
      账号已删除时同样回退 uid 前 8 位，不留空。Run with Node.
*/
const assert = require('assert');
const {dashboardHtml, dashboardScript} = require('./_dashboard_source.js');

const html = dashboardHtml();
const script = dashboardScript();

// One persistent element per id, so the rendered table can be read back.
const elements = new Map();
const element = id => {
  if (!elements.has(id)) {
    elements.set(id, {
      id, innerHTML: '', textContent: '', value: '', className: '', style: {},
      classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
      addEventListener(){}, querySelector(){ return null; }, querySelectorAll(){ return []; },
      appendChild(){}, focus(){}, setAttribute(){}, getAttribute(){ return ''; },
    });
  }
  return elements.get(id);
};
const TBODY = element('creditHistoryBody');
global.document = {
  getElementById: element,
  querySelector: sel => (sel === '#creditHistoryTable tbody' ? TBODY : null),
  querySelectorAll: () => [],
  addEventListener(){}, createElement: () => element('created'),
  body: element('body'), head: element('head'), documentElement: element('html'),
};
global.window = {addEventListener(){}, location: {href: '', search: ''},
  matchMedia: () => ({matches: false, addEventListener(){}}), ACCOUNTS: []};
global.ACCOUNTS = global.window.ACCOUNTS;
global.localStorage = {getItem(){ return null; }, setItem(){}, removeItem(){}};
global.sessionStorage = global.localStorage;
global.navigator = {userAgent: 'node'};
global.setInterval = () => 0;
global.setTimeout = () => 0;
global.location = {href: '', search: '', hash: ''};
global.alert = () => {};
global.confirm = () => false;
global.fetch = () => Promise.resolve({
  status: 200, ok: true,
  json: () => Promise.resolve({}),
  text: () => Promise.resolve('{}'),
});

const DATA = {
  credits: [
    {iso: '2026-10-08T15:30:42', model: 'deepseek-v4.1-flash',
     account: '1c0dd7a8b9c0', credit: 0.59, total_tokens: 8831},
    {iso: '2026-10-08T08:57:39', model: 'gpt-5.6-sol',
     account: '5e93a7361122', credit: 0.03, total_tokens: 57},
    {iso: '2026-10-08T08:00:00', model: 'gpt-5.6-sol',
     account: '', credit: 0.01, total_tokens: 12},
  ],
};

const api = new Function(script + `
  return { renderCreditHistory };`)();

let checks = 0;
const check = (label, cond, extra) => {
  checks += 1;
  assert.ok(cond, label + (extra ? '  [' + extra + ']' : ''));
};

// ---- ① 表头固定 ----------------------------------------------------------
const thead = html.match(/<table class="data-cards" id="creditHistoryTable">[\s\S]*?<\/thead>/);
check('积分扣减历史表头仍是 5 列',
      thead && (thead[0].match(/<th>/g) || []).length === 5,
      thead ? String((thead[0].match(/<th>/g) || []).length) : 'thead not found');
check('表头列名没变',
      thead && ['时间', '模型', '账号', '积分', 'Token']
        .every(name => thead[0].includes('<th>' + name + '</th>')));
const sticky = html.match(/#creditHistoryTable thead th\{[^}]*\}/);
check('表头 th 声明了 sticky 定位',
      sticky && /position:sticky/.test(sticky[0]),
      sticky ? sticky[0].replace(/\s+/g, ' ') : 'rule not found');
check('sticky 表头钉在容器顶部',
      sticky && /top:0/.test(sticky[0]),
      sticky ? sticky[0].replace(/\s+/g, ' ') : 'rule not found');
check('外层容器确实会纵向滚动（否则 sticky 无意义）',
      /overflow-x:auto;max-height:260px/.test(html));

// ---- ② 账号列带昵称 ------------------------------------------------------
// 断言按「行」读渲染结果：一行就是一次扣减记录，账号单元格取表头里「账号」
// 那一列。整表子串搜索既会被一个无害的属性变化绊倒（给 <td> 加个 class，
// `<td title="…">` 就不再匹配），也看不出昵称到底挂在哪一行、哪一列。
const cellOf = row => [...row.matchAll(/<td\b([^>]*)>([\s\S]*?)<\/td>/g)].map(m => ({
  attrs: m[1],
  text: m[2],
  title: (m[1].match(/(?:^|\s)title="([^"]*)"/) || [])[1] || '',
}));
const rowFor = (html, iso) => [...html.matchAll(/<tr>([\s\S]*?)<\/tr>/g)]
  .map(m => cellOf(m[1]))
  .find(cells => cells[0] && cells[0].text === iso) || [];
const headerNames = thead
  ? [...thead[0].matchAll(/<th>([\s\S]*?)<\/th>/g)].map(m => m[1].trim()) : [];
const ACCOUNT_COL = headerNames.indexOf('账号');
const accountOf = (html, iso) => rowFor(html, iso)[ACCOUNT_COL] || null;
// 昵称是中文，账号单元格不该套等宽字体：看的是那个单元格自己（含内部标记），
// 而不是整张表里某一段精确的 class 字符串。
const notMono = cell => !!cell && !/\bclass="[^"]*\bmono\b/.test(cell.attrs + cell.text);

let body = '';
const checkAccount = (label, iso, text, title) => {
  const cell = accountOf(body, iso);
  check(label, !!cell && cell.text === text && cell.title === title,
        iso + ' -> ' + JSON.stringify(cell));
};

// 账号还没加载完：只能用 uid 前 8 位兜底。
window.ACCOUNTS = [];
api.renderCreditHistory(DATA);
body = TBODY.innerHTML;
checkAccount('账号未加载时回退 uid 前 8 位',
             '2026-10-08T15:30:42', '1c0dd7a8', '1c0dd7a8b9c0');
checkAccount('uid 前 8 位不是硬截断（第二位账号同样处理）',
             '2026-10-08T08:57:39', '5e93a736', '5e93a7361122');
checkAccount('账号为空时不渲染空白', '2026-10-08T08:00:00', '—', '');

// 账号到位后补画：昵称替换 uid；不在池中的账号（已删除）仍回退 uid。
window.ACCOUNTS = [{uid: '1c0dd7a8b9c0', nickname: '老王'}];
api.renderCreditHistory();          // 不带参数 = 用上一次的数据重画
body = TBODY.innerHTML;
checkAccount('账号到位后补画显示昵称', '2026-10-08T15:30:42', '老王', '1c0dd7a8b9c0');
checkAccount('账号不在池中（已删除）仍回退 uid 前 8 位',
             '2026-10-08T08:57:39', '5e93a736', '5e93a7361122');

// 重新传入数据也要更新缓存。
window.ACCOUNTS = [{uid: '1c0dd7a8b9c0', nickname: '张三'}];
api.renderCreditHistory({credits: [DATA.credits[0]]});
body = TBODY.innerHTML;
checkAccount('传入新数据后昵称跟随更新', '2026-10-08T15:30:42', '张三', '1c0dd7a8b9c0');
check('旧的昵称不会留在表里', !body.includes('老王'), body.slice(0, 200));
check('账号单元格不再强制等宽字体（昵称是中文）',
      notMono(accountOf(body, '2026-10-08T15:30:42')),
      JSON.stringify(accountOf(body, '2026-10-08T15:30:42')));
check('积分与 token 仍按原样渲染',
      body.includes('>0.59<') && body.includes('>8,831<'), body.slice(0, 400));

// 空数据走占位行。
api.renderCreditHistory({credits: []});
check('无记录时保留占位行',
      TBODY.innerHTML.includes('没有积分扣减记录') &&
      TBODY.innerHTML.includes('colspan="5"'));

console.log('credit-history assertions passed (' + checks + ' checks)');
