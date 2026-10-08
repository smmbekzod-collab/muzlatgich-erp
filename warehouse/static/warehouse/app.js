if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
document.querySelectorAll('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',event=>{const submit=event.submitter;if(submit){setTimeout(()=>{submit.disabled=true;submit.textContent='Saqlanmoqda…'},0)}}));
function connection(){let banner=document.getElementById('connection');if(!navigator.onLine&&!banner){banner=document.createElement('div');banner.id='connection';banner.className='offline';banner.textContent='Internet uzildi. Hujjat yuborish uchun ulanishni tiklang.';document.body.prepend(banner)}if(navigator.onLine&&banner)banner.remove()}
addEventListener('online',connection);addEventListener('offline',connection);connection();
