(function(){
  let qrModal, html5Qr, lastScanTime = 0, isProcessing = false, scannerReady = false;

  function setInlineMsg(type, text){
    const box = document.getElementById('qrInlineMsg');
    if(!box) return;
    box.className = '';
    if(type === 'ok') box.className = 'text-success';
    if(type === 'err') box.className = 'text-danger';
    box.textContent = text || '';
  }

  async function fetchPatientByEmail(email){
    try{
      const resp = await fetch('/patients/api/qr-scan/?email=' + encodeURIComponent(email));
      if(!resp.ok) return null;
      const data = await resp.json();
      if(data && data.success && data.patient) return data.patient;
      return null;
    }catch(_){ return null; }
  }

  async function handleReceptionEmail(email){
    const patient = await fetchPatientByEmail(email);
    if(patient && patient.patient_code){
      const codeInput = document.getElementById('patientCodeInput');
      if(codeInput){ codeInput.value = patient.patient_code; codeInput.focus(); }
      setInlineMsg('ok', '✅ Patient Found: ' + (patient.email || email));
    } else {
      setInlineMsg('err', '❌ Patient not found in system.');
    }
  }

  function onScanSuccess(decodedText){
    if (!scannerReady) return;
    if (!decodedText || decodedText.trim().length < 3) return;
    const now = Date.now();
    if (now - lastScanTime < 1500 || isProcessing) return;
    lastScanTime = now;
    isProcessing = true;
    try{ html5Qr && html5Qr.stop(); }catch(_){ }
    const statusEl = document.getElementById('scanner-status');
    if (statusEl) statusEl.textContent = 'Processing QR code...';
    // parse email from QR or use raw
    let email = (decodedText || '').trim();
    const m = email.match(/email:([^;\s]+)/i);
    if(m){ email = (m[1]||'').trim(); }
    handleReceptionEmail(email).finally(()=>{
      isProcessing = false;
    });
  }

  function onScanFailure(_){ /* ignore continuous failures */ }

  function startScanner(camId){
    const el = document.getElementById('qr-reader');
    if(!el) return;
    if(html5Qr){ try{ html5Qr.stop().then(()=>html5Qr.clear()).catch(()=>{}); }catch(_){ } }
    html5Qr = new Html5Qrcode('qr-reader');
    scannerReady = false;
    html5Qr.start(camId, { fps:2, qrbox:{ width:250, height:250 } }, onScanSuccess, onScanFailure)
      .then(()=>{ const s=document.getElementById('scanner-status'); if(s) s.textContent='Point camera at QR'; setTimeout(()=>{ scannerReady = true; }, 800); })
      .catch(()=>{ const s=document.getElementById('scanner-status'); if(s) s.textContent='Camera failed to start'; });
  }

  // Open modal
  document.addEventListener('click', function(e){
    const btn = e.target.closest('.qr-scan-btn');
    if(!btn) return;
    e.preventDefault();
    setInlineMsg('', '');
    qrModal = new bootstrap.Modal(document.getElementById('qrScannerModal'));
    qrModal.show();
    // Initialize camera
    setTimeout(()=>{
      Html5Qrcode.getCameras().then(cams=>{
        const id = (cams && cams[0] && cams[0].id) || undefined;
        startScanner(id);
      }).catch(()=> startScanner());
    }, 300);
  });

  // Fallback email submit
  document.getElementById('qrEmailGo')?.addEventListener('click', function(){
    const v = (document.getElementById('qrEmailFallback')||{}).value || '';
    if(qrModal) qrModal.hide();
    handleReceptionEmail(v);
  });

  // Refresh camera
  document.getElementById('refreshCameraBtn')?.addEventListener('click', function(){
    Html5Qrcode.getCameras().then(cams=>{
      const id = (cams && cams[0] && cams[0].id) || undefined;
      startScanner(id);
    }).catch(()=> startScanner());
  });

  // Confirmation modal buttons now just close; we don't navigate
  document.getElementById('qrConfirmProceed')?.addEventListener('click', function(){
    const m = bootstrap.Modal.getInstance(document.getElementById('qrConfirmationModal'));
    if(m) m.hide();
  });
  document.getElementById('qrConfirmCancel')?.addEventListener('click', function(){
    const m = bootstrap.Modal.getInstance(document.getElementById('qrConfirmationModal'));
    if(m) m.hide();
  });

  // Cleanup on modal close
  document.getElementById('qrScannerModal')?.addEventListener('hidden.bs.modal', function(){
    if(html5Qr){ try{ html5Qr.stop().then(()=>html5Qr.clear()).catch(()=>{}); }catch(_){ } html5Qr = null; }
    isProcessing = false;
    scannerReady = false;
  });
})();


