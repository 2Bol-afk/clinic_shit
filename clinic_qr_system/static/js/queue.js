(function(){
  function getCookie(name){
    const m = document.cookie.match('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, '\\$1') + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : null;
  }
  async function post(url, form){
    const fd = form instanceof FormData ? form : new FormData();
    let csrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if(!csrf){
      const c = getCookie('csrftoken');
      if(c){ fd.append('csrfmiddlewaretoken', c); }
    } else {
      fd.append('csrfmiddlewaretoken', csrf.value);
    }
    const resp = await fetch(url, { method:'POST', headers:{ 'X-Requested-With':'XMLHttpRequest' }, body: fd });
    if(!resp.ok){ throw new Error('Request failed'); }
    return resp.json();
  }
  function moveCard(el, targetSel){
    const target = document.querySelector(targetSel);
    if(!el || !target) return;
    el.parentNode && el.parentNode.removeChild(el);
    target.appendChild(el);
  }
  document.addEventListener('click', async function(e){
    const claimBtn = e.target.closest('[data-action="claim"]');
    if(claimBtn){
      e.preventDefault();
      const url = claimBtn.getAttribute('data-url');
      const card = claimBtn.closest('[data-card]');
      const fd = new FormData();
      const rid = claimBtn.getAttribute('data-id');
      if(rid){ fd.append('reception_visit_id', rid); }
      try{
        const data = await post(url, fd);
        if(data && data.success){
          moveCard(card, '[data-container="claimed"]');
          // Transform Claim button into Verify button that opens modal
          const btn = card.querySelector('[data-action="claim"]');
          if(btn){
            btn.removeAttribute('data-action');
            btn.removeAttribute('data-url');
            btn.removeAttribute('data-id');
            btn.setAttribute('type','button');
            btn.setAttribute('data-bs-toggle','modal');
            btn.setAttribute('data-bs-target','#verifyModal');
            btn.setAttribute('data-visit', rid || '');
            btn.classList.remove('btn-outline-primary');
            btn.classList.add('btn-outline-secondary');
            btn.innerHTML = '<i class="bi bi-qr-code-scan me-1"></i>Verify';
          }
        }
      }catch(_){ /* handle error */ }
      return;
    }
    const finishBtn = e.target.closest('[data-action="finish"]');
    if(finishBtn){
      e.preventDefault();
      const url = finishBtn.getAttribute('data-url');
      const card = finishBtn.closest('[data-card]');
      try{
        const data = await post(url);
        if(data && data.success){
          moveCard(card, '[data-container="finished"]');
        }
      }catch(_){ /* handle error */ }
    }
  });
})();
