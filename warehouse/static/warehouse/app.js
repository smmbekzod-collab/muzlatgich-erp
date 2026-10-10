if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
document.querySelectorAll('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',event=>{const submit=event.submitter;if(submit){setTimeout(()=>{submit.disabled=true;submit.textContent='Saqlanmoqda…'},0)}}));
function connection(){let banner=document.getElementById('connection');if(!navigator.onLine&&!banner){banner=document.createElement('div');banner.id='connection';banner.className='offline';banner.textContent='Internet uzildi. Hujjat yuborish uchun ulanishni tiklang.';document.body.prepend(banner)}if(navigator.onLine&&banner)banner.remove()}
addEventListener('online',connection);addEventListener('offline',connection);connection();

document.querySelectorAll('[data-dispatch-form]').forEach(form => {
  const fill = form.querySelector('[data-fill-all]');
  const boxes = form.querySelector('[name="boxes"]');
  const gross = form.querySelector('[name="gross"]');
  const tare = form.querySelector('[name="tare"]');
  const confirm = form.querySelector('[data-final-confirm]');
  const changed = form.querySelector('[data-preview-changed]');
  let original = null;
  if (confirm) {
    original = Array.from(form.querySelectorAll('input,select,textarea'))
      .filter(el => el.name !== 'csrfmiddlewaretoken' && el.name !== 'preview_token')
      .map(el => [el.name,el.value]);
    function invalidate() {
      const altered = original.some(([name,value]) => {
        const field = form.elements.namedItem(name);
        return field && field.value !== value;
      });
      confirm.disabled = !!altered;
      if (changed) {
        changed.hidden = !altered;
        if (altered) changed.textContent = 'Maydonlar o‘zgardi. Tasdiqlash uchun summani qayta hisoblang.';
      }
    }
    form.addEventListener('input', invalidate);
    form.addEventListener('change', invalidate);
  }
  if (fill && boxes && gross && tare) {
    fill.addEventListener('click', () => {
      boxes.value = fill.dataset.boxes;
      gross.value = fill.dataset.gross;
      tare.value = fill.dataset.tare;
      boxes.dispatchEvent(new Event('input', {bubbles:true}));
      gross.dispatchEvent(new Event('input', {bubbles:true}));
    });
  }
});
