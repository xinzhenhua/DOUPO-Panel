// ============================================================================
// test_helpers.js — 所有测试文件共用的DOM/浏览器环境模拟 + 断言工具
// ============================================================================
// 用法：const H = require('./test_helpers'); 然后用 H.makeEl/H.check/H.printSummary 等

const elements = {};

function makeEl(id){
  if(!elements[id]) elements[id] = {
    id, value:'', textContent:'', className:'', innerHTML:'',
    classList:{
      list:new Set(),
      add(c){ this.list.add(c); },
      remove(c){ this.list.delete(c); },
      contains(c){ return this.list.has(c); },
      toggle(c, force){
        if(force===undefined){
          if(this.list.has(c)){ this.list.delete(c); return false; }
          this.list.add(c); return true;
        }
        if(force){ this.list.add(c); } else { this.list.delete(c); }
        return force;
      }
    }
  };
  return elements[id];
}

function resetElements(){
  Object.keys(elements).forEach(k => delete elements[k]);
}

// ---- 全局浏览器环境模拟(仪表盘代码里用到的document/window/localStorage/fetch/navigator) ----
global.document = { getElementById(id){ return makeEl(id); }, addEventListener(){} };
if(!global.window) global.window = {};
global.localStorage = { data:{}, getItem(k){ return null; }, setItem(k,v){} };
if(!global.fetch) global.fetch = async()=>({ok:false});
// ★ 重要：Node.js v21+内置了只读的navigator全局对象(用getter定义，没有setter)，
//   直接用 global.navigator = {...} 赋值会被静默忽略。必须用Object.defineProperty
//   强制覆盖(内置的navigator对象是configurable:true，所以能覆盖)。
Object.defineProperty(global, 'navigator', { value: { clipboard: null }, configurable: true, writable: true });

function setClipboardMock(writeTextFn){
  Object.defineProperty(global, 'navigator', {
    value: { clipboard: { writeText: writeTextFn } },
    configurable: true, writable: true,
  });
}

// ---- Date模拟：部分测试需要模拟"当前月份"来验证时间感知加权逻辑 ----
const RealDate = Date;
let mockedMonth = null; // null=不模拟，用真实当前月份

class MockDate extends RealDate {
  constructor(...args){
    if(args.length === 0){ super(); this._useMock = true; }
    else { super(...args); this._useMock = false; }
  }
  getMonth(){
    if(this._useMock && mockedMonth !== null) return mockedMonth - 1;
    return super.getMonth();
  }
}

function setMockedMonth(m){ mockedMonth = m; global.Date = MockDate; }
function clearMockedMonth(){ mockedMonth = null; global.Date = RealDate; }

// ---- 从index.html提取<script>内容，供eval()加载仪表盘的实际JS逻辑 ----
function loadDashboardJs(){
  const fs = require('fs');
  const path = require('path');
  const htmlPath = path.join(__dirname, '..', 'index.html');
  const content = fs.readFileSync(htmlPath, 'utf8');
  const start = content.indexOf('<script>');
  const end = content.lastIndexOf('</script>');
  return content.slice(start + 8, end);
}

// ---- 断言与计数 ----
let pass = 0, fail = 0;

function check(desc, cond){
  if(cond){ pass++; console.log('✅', desc); }
  else { fail++; console.log('❌', desc); }
}

function printSummary(){
  console.log('');
  console.log(`结果：${pass}项通过，${fail}项失败`);
  if(fail > 0) process.exit(1);
}

module.exports = {
  makeEl, elements, resetElements,
  setMockedMonth, clearMockedMonth,
  loadDashboardJs, setClipboardMock,
  check, printSummary,
};
