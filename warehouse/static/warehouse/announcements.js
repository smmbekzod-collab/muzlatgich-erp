(() => {
  const select = document.getElementById('select-groups');
  if (select) select.addEventListener('click', () => {
    const boxes = [...document.querySelectorAll('input[name="destinations"]')];
    const checked = !boxes.every(box => box.checked);
    boxes.forEach(box => { box.checked = checked; });
    select.textContent = checked ? 'Tanlovni bekor qilish' : 'Barchasini tanlash';
  });
  const form = document.getElementById('announcement-send');
  if (!form) return;
  let busy = false;
  async function send(event) {
    if (event) event.preventDefault();
    if (busy) return;
    busy = true;
    const button = form.querySelector('button');
    const progress = document.getElementById('send-progress');
    button.disabled = true;
    try {
      let remaining;
      do {
        progress.textContent = 'Guruhlarga yuborilmoqda…';
        const response = await fetch(form.action, {
          method: 'POST', body: new FormData(form), credentials: 'same-origin',
          headers: {'X-Requested-With': 'XMLHttpRequest'}
        });
        if (!response.ok) throw new Error('Yuborish to‘xtadi. Sahifani yangilab natijani tekshiring.');
        const result = await response.json();
        remaining = result.remaining;
        progress.textContent = `Yuborish kutilayotgan guruhlar: ${remaining}`;
      } while (remaining > 0);
      location.replace(location.pathname);
    } catch (error) {
      progress.textContent = 'Ulanish uzildi. Sahifani yangilang: yuborilgan xabarlar qaytarilmaydi, qolganlarini davom ettirishingiz mumkin.';
    } finally {
      busy = false;
      button.disabled = false;
    }
  }
  form.addEventListener('submit', send);
  if (form.dataset.autostart === '1') send();
})();
