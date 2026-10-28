(() => {
 'use strict';
 const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
 const latin='0123456789',persian='۰۱۲۳۴۵۶۷۸۹',arabic='٠١٢٣٤٥٦٧٨٩';
 const toLatin=s=>String(s??'').replace(/[۰-۹٠-٩]/g,c=>{const i=persian.indexOf(c);return i>=0?latin[i]:latin[arabic.indexOf(c)]}).replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/ـ/g,'');
 const toFa=s=>String(s).replace(/[0-9]/g,c=>persian[Number(c)]);
 const root=document.documentElement,themeKey='ahan-theme';
 root.dataset.theme=localStorage.getItem(themeKey)||(window.matchMedia?.('(prefers-color-scheme: dark)').matches?'dark':'light');
 const themeButton=$('#theme-toggle');
 function themeIcon(){if(!themeButton)return;const dark=root.dataset.theme==='dark';themeButton.setAttribute('aria-label',dark?'تغییر به حالت روشن':'تغییر به حالت تیره');const use=themeButton.querySelector('use');if(use)use.setAttribute('href',dark?'/static/icons.svg#sun':'/static/icons.svg#moon');}
 themeButton?.addEventListener('click',()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.setItem(themeKey,root.dataset.theme);themeIcon();});themeIcon();
 const sidebar=$('#app-sidebar');
 if(localStorage.getItem('ahan-sidebar-collapsed')==='1')root.dataset.sidebar='collapsed';
 $('#sidebar-collapse')?.addEventListener('click',()=>{const next=root.dataset.sidebar==='collapsed'?'':'collapsed';root.dataset.sidebar=next;localStorage.setItem('ahan-sidebar-collapsed',next?'1':'0');});
 $('#mobile-menu')?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
 let restoreFocus=null;
 const overlay=$('#command-palette'),input=$('#command-input'),list=$('#command-list'),globalSearch=$('#global-search');
 const commands=[
  ['فروش جدید','F2','/sales','فروش sale'],['خرید جدید','F3','/purchases','خرید purchase'],['خدمات','صفحه خدمات','/services','خدمات service'],['ثبت هزینه','F4','/expenses','هزینه expenses'],['کالاها و موجودی','انبار','/products','کالا انبار product'],['انبارگردانی','ثبت شمارش فیزیکی','/inventory','انبارگردانی موجودی count'],['مرجوعی خرید و فروش','مرجوعی','/returns','مرجوعی برگشت فروش خرید'],['پیشنهاد خرید','برآورد سفارش','/buy-advice','پیشنهاد سفارش خرید موجودی'],['صندوق و بانک','گردش حساب','/cash','صندوق بانک گردش نقدی'],['طرف حساب‌ها','مشتری و فروشنده','/parties','مشتری فروشنده مانده حساب'],['قیمت روز','روند تاریخچه قیمت','/prices','قیمت بازار نمودار'],['گزارش‌ها','سود و جریان نقدی','/reports','گزارش سود ماهانه'],['گزارش ممیزی','تاریخچه عملیات','/audit','ممیزی رخداد تاریخچه'],['پشتیبان‌گیری','تنظیمات','/settings','پشتیبان backup'],['سیستم طراحی','راهنمای اجزا','/design','طراحی design']
 ];
 function clear(n){while(n?.firstChild)n.removeChild(n.firstChild);}
 function paint(q=''){clear(list);const needle=toLatin(q).toLocaleLowerCase('fa');const found=commands.filter(c=>!needle||toLatin(c.join(' ')).toLocaleLowerCase('fa').includes(needle));found.forEach(c=>{const a=document.createElement('a');a.className='command-item';a.href=c[2];const label=document.createElement('span');label.textContent=c[0];const meta=document.createElement('span');meta.className='command-meta';meta.textContent=c[1];a.append(label,meta);list.append(a);});if(!found.length){const p=document.createElement('p');p.className='empty';p.textContent='موردی پیدا نشد؛ واژه دیگری جستجو کن.';list.append(p);}}
 function openPalette(q=''){if(!overlay)return;restoreFocus=document.activeElement;overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');paint(q);if(input){input.value=q;input.focus();}}
 function closePalette(){overlay?.classList.remove('open');overlay?.setAttribute('aria-hidden','true');if(restoreFocus?.focus)restoreFocus.focus();}
 $('#command-open')?.addEventListener('click',()=>openPalette());$('#command-close')?.addEventListener('click',closePalette);globalSearch?.addEventListener('focus',()=>openPalette(globalSearch.value));globalSearch?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();openPalette(globalSearch.value);}});input?.addEventListener('input',()=>paint(input.value));overlay?.addEventListener('click',e=>{if(e.target===overlay)closePalette();});
 const confirmDialog=$('#confirm-dialog'),phraseInput=$('#confirm-phrase'),confirmAccept=$('#confirm-accept');let confirmWord='';
 $('#confirm-cancel')?.addEventListener('click',()=>confirmDialog?.close());phraseInput?.addEventListener('input',()=>{if(confirmAccept)confirmAccept.disabled=toLatin(phraseInput.value).trim()!==toLatin(confirmWord).trim();});
 document.addEventListener('click',e=>{const trigger=e.target.closest('[data-confirm]');if(!trigger)return;e.preventDefault();if(!confirmDialog)return;confirmWord=trigger.dataset.confirmPhrase||'تأیید';$('#confirm-title').textContent='تأیید عملیات';$('#confirm-description').textContent=trigger.dataset.confirm||'این عملیات را تأیید می‌کنی؟';phraseInput.value='';confirmAccept.disabled=Boolean(trigger.dataset.confirmPhrase);confirmDialog.showModal();confirmAccept.onclick=()=>{if(trigger.dataset.confirmPhrase&&toLatin(phraseInput.value).trim()!==toLatin(confirmWord).trim())return;confirmDialog.close();if(trigger.tagName==='FORM')trigger.submit();else if(trigger.href)location.href=trigger.href;};});
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();return;}if(e.key==='Escape'){closePalette();if(confirmDialog?.open)confirmDialog.close();sidebar?.classList.remove('open');return;}if(e.key==='F2'){e.preventDefault();location.href='/sales';}if(e.key==='F3'){e.preventDefault();location.href='/purchases';}if(e.key==='F4'){e.preventDefault();location.href='/expenses';}if(e.key==='?'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName||'')){openPalette('میان‌بر');}if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName||'')){e.preventDefault();globalSearch?.focus();}});
 const small=['','یک','دو','سه','چهار','پنج','شش','هفت','هشت','نه','ده','یازده','دوازده','سیزده','چهارده','پانزده','شانزده','هفده','هجده','نوزده'];
 const tens=['','','بیست','سی','چهل','پنجاه','شصت','هفتاد','هشتاد','نود'],hundreds=['','یکصد','دویست','سیصد','چهارصد','پانصد','ششصد','هفتصد','هشتصد','نهصد'];
 function less1000(n){const a=[];if(n>=100){a.push(hundreds[Math.floor(n/100)]);n%=100;}if(n>=20){a.push(tens[Math.floor(n/10)]);n%=10;}if(n>0)a.push(small[n]);return a.join(' و ');}
 function words(n){if(!Number.isFinite(n)||n<0||n>999999999999)return '';if(n===0)return 'صفر';const scales=['','هزار','میلیون','میلیارد'];const parts=[];let i=0;while(n>0){const chunk=n%1000;if(chunk){const w=less1000(chunk);parts.unshift(scales[i]?w+' '+scales[i]:w);}n=Math.floor(n/1000);i++;}return parts.join(' و ');}
 function amountWords(n){const number=Number(toLatin(n).replace(/[٬,\s]/g,''));return Number.isFinite(number)&&number>=0?words(Math.floor(number))+' تومان':'';}
 $$('[data-money="true"]').forEach(el=>{const wordsNode=$('[data-words-for="'+el.name+'"]');const format=()=>{let raw=toLatin(el.value).replace(/[٬,\s]/g,'').replace(/[^0-9.\-]/g,'');const isNeg=raw.startsWith('-');raw=raw.replace(/-/g,'');const pieces=raw.split('.');const head=(pieces.shift()||'').replace(/^0+(?=\d)/,'');const grouped=head.replace(/\B(?=(\d{3})+(?!\d))/g,'٬');el.value=(isNeg?'-':'')+toFa(grouped+(pieces.length?'.'+pieces.join(''):''));if(wordsNode)wordsNode.textContent=amountWords(el.value);};el.addEventListener('input',format);el.addEventListener('blur',format);format();});
 $$('[data-numeric="true"]:not([data-money="true"])').forEach(el=>el.addEventListener('input',()=>{el.value=toFa(toLatin(el.value));}));
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);nodes.forEach(n=>{if(n.parentElement&&!['SCRIPT','STYLE','TEXTAREA','INPUT'].includes(n.parentElement.tagName))n.nodeValue=toFa(n.nodeValue);});
 $$('table thead th').forEach((th,index)=>{th.tabIndex=0;th.setAttribute('role','button');th.setAttribute('aria-label',(th.textContent||'').trim()+'؛ مرتب‌سازی');const sort=()=>{const table=th.closest('table'),tbody=table?.tBodies[0];if(!tbody)return;const rows=[...tbody.rows],asc=th.dataset.sort!=='asc';rows.sort((a,b)=>{const x=toLatin(a.cells[index]?.textContent||'').replace(/[٬,]/g,'').trim(),y=toLatin(b.cells[index]?.textContent||'').replace(/[٬,]/g,'').trim(),nx=Number(x),ny=Number(y);return Number.isFinite(nx)&&Number.isFinite(ny)?(nx-ny)*(asc?1:-1):x.localeCompare(y,'fa')*(asc?1:-1);});rows.forEach(r=>tbody.append(r));th.dataset.sort=asc?'asc':'desc';};th.addEventListener('click',sort);th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();sort();}});});
 $('form').forEach(form=>form.addEventListener('submit',e=>{if(form.dataset.confirmSubmit==='1'&&!window.confirm(form.dataset.confirmMessage||'از انجام این عملیات مطمئنی؟')){e.preventDefault();return;}if(!form.checkValidity()){e.preventDefault();const first=form.querySelector(':invalid');first?.focus();first?.scrollIntoView({behavior:'smooth',block:'center'});return;}const button=form.querySelector('button[type="submit"],button:not([type])');if(button&&!button.disabled){button.disabled=true;button.dataset.originalText=button.textContent;button.textContent='در حال ذخیره…';}}));
 const jalaliMonths=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
 const jalaliWeekdays=['ش','ی','د','س','چ','پ','ج'];
 function j2g(jy,jm,jd){
  let y=jy+1595,days=-355668+365*y+Math.floor(y/33)*8+Math.floor(((y%33)+3)/4)+jd;
  if(jm<7)days+=(jm-1)*31;else days+=186+(jm-7)*30;
  let gy=Math.floor(days/146097)*400;days%=146097;
  if(days>36524){gy+=Math.floor((days-1)/36524)*100;days=(days-1)%36524;if(days>=365)days++;}
  gy+=Math.floor(days/1461)*4;days%=1461;
  if(days>365){gy+=Math.floor((days-1)/365);days=(days-1)%365;}
  let gd=days+1,leap=(gy%4===0&&gy%100!==0)||gy%400===0,md=[0,31,leap?29:28,31,30,31,30,31,31,30,31,30,31],gm=1;
  while(gm<=12&&gd>md[gm]){gd-=md[gm];gm++;}
  return [gy,gm,gd];
 }
 function parseJalali(value,fallback){
  const parts=toLatin(value||'').trim().replace(/-/g,'/').split('/');
  if(parts.length===3&&parts.every(p=>/^\d+$/.test(p))){const d=parts.map(Number);if(d[0]>1000&&d[1]>=1&&d[1]<=12&&d[2]>=1&&d[2]<=31)return d;}
  return fallback.slice();
 }
 function jalaliDays(year,month){
  const a=j2g(year,month,1),b=month===12?j2g(year+1,1,1):j2g(year,month+1,1);
  return Math.round((Date.UTC(b[0],b[1]-1,b[2])-Date.UTC(a[0],a[1]-1,a[2]))/86400000);
 }
 function initJalaliPicker(el){
  const wrap=el.closest('.field'),inputWrap=el.closest('.input-wrap');if(!wrap||!inputWrap)return;
  const today=parseJalali(el.dataset.today,[1400,1,1]);let view=parseJalali(el.value,today),viewYear=view[0],viewMonth=view[1];
  const trigger=document.createElement('button');trigger.type='button';trigger.className='secondary sm date-picker-trigger';trigger.textContent='تقویم';trigger.setAttribute('aria-label','باز کردن تقویم شمسی');trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-expanded','false');inputWrap.append(trigger);
  const panel=document.createElement('div');panel.className='jalali-date-picker';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','تقویم شمسی');wrap.append(panel);
  const close=()=>{panel.hidden=true;trigger.setAttribute('aria-expanded','false');};
  const updateInput=d=>{el.value=toFa(d.map((x,i)=>String(x).padStart(i===0?4:2,'0')).join('/'));el.dispatchEvent(new Event('change',{bubbles:true}));};
  function render(){
   panel.replaceChildren();
   const header=document.createElement('div');header.className='jalali-calendar-header';
   const prev=document.createElement('button');prev.type='button';prev.className='secondary sm';prev.textContent='‹';prev.setAttribute('aria-label','ماه قبل');
   const title=document.createElement('strong');title.textContent=jalaliMonths[viewMonth-1]+' '+toFa(viewYear);
   const next=document.createElement('button');next.type='button';next.className='secondary sm';next.textContent='›';next.setAttribute('aria-label','ماه بعد');
   prev.addEventListener('click',()=>{viewMonth--;if(viewMonth<1){viewMonth=12;viewYear--;}render();});
   next.addEventListener('click',()=>{viewMonth++;if(viewMonth>12){viewMonth=1;viewYear++;}render();});
   header.append(prev,title,next);
   const weekdays=document.createElement('div');weekdays.className='jalali-calendar-weekdays';
   jalaliWeekdays.forEach(day=>{const x=document.createElement('span');x.textContent=day;weekdays.append(x);});
   const grid=document.createElement('div');grid.className='jalali-calendar-days';grid.setAttribute('role','grid');
   const first=j2g(viewYear,viewMonth,1),offset=(new Date(Date.UTC(first[0],first[1]-1,first[2])).getUTCDay()+1)%7;
   for(let i=0;i<offset;i++){const empty=document.createElement('span');empty.className='jalali-calendar-empty';grid.append(empty);}
   const selected=parseJalali(el.value,today),count=jalaliDays(viewYear,viewMonth);
   for(let day=1;day<=count;day++){
    const b=document.createElement('button');b.type='button';b.className='jalali-calendar-day';b.textContent=toFa(day);b.setAttribute('role','gridcell');
    b.setAttribute('aria-label',toFa(viewYear+'/'+String(viewMonth).padStart(2,'0')+'/'+String(day).padStart(2,'0')));
    if(selected[0]===viewYear&&selected[1]===viewMonth&&selected[2]===day){b.classList.add('selected');b.setAttribute('aria-selected','true');}
    if(today[0]===viewYear&&today[1]===viewMonth&&today[2]===day)b.classList.add('today');
    b.addEventListener('click',()=>{updateInput([viewYear,viewMonth,day]);close();el.focus();});grid.append(b);
   }
   const footer=document.createElement('div');footer.className='jalali-calendar-footer';
   const jump=document.createElement('button');jump.type='button';jump.className='secondary sm';jump.textContent='رفتن به امروز';jump.addEventListener('click',()=>{viewYear=today[0];viewMonth=today[1];render();});
   const done=document.createElement('button');done.type='button';done.className='secondary sm';done.textContent='بستن';done.addEventListener('click',close);footer.append(jump,done);
   panel.append(header,weekdays,grid,footer);
  }
  const open=()=>{const d=parseJalali(el.value,today);viewYear=d[0];viewMonth=d[1];render();panel.hidden=false;trigger.setAttribute('aria-expanded','true');};
  trigger.addEventListener('click',()=>panel.hidden?open():close());
  el.addEventListener('change',()=>{const d=parseJalali(el.value,today);viewYear=d[0];viewMonth=d[1];if(!panel.hidden)render();});
  el.addEventListener('keydown',e=>{if((e.altKey&&e.key==='ArrowDown')||e.key==='F4'){e.preventDefault();open();}else if(e.key==='Escape'&&!panel.hidden){close();trigger.focus();}});
  document.addEventListener('pointerdown',e=>{if(!wrap.contains(e.target)&&!panel.hidden)close();});
 }
 $$('[data-date-input="true"]').forEach(el=>{el.value=toFa(toLatin(el.value));initJalaliPicker(el);});
 $('[data-today]').forEach(el=>{const wrap=el.closest('.field');if(!wrap)return;const controls=document.createElement('div');controls.className='date-shortcuts';[['امروز',el.dataset.today],['دیروز',el.dataset.yesterday]].forEach(([label,value])=>{if(!value)return;const b=document.createElement('button');b.type='button';b.className='secondary sm';b.textContent=label;b.addEventListener('click',()=>{el.value=toFa(toLatin(value));el.dispatchEvent(new Event('change',{bubbles:true}));});controls.append(b);});wrap.append(controls);});
 })();