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
    console.log('handleReceptionEmail called with email:', email);
    const patient = await fetchPatientByEmail(email);
    console.log('Patient data received:', patient);
    if(patient && patient.patient_code){
      // Show the same patient confirmation modal as QR scanning
      console.log('Showing patient confirmation modal');
      showPatientConfirmationModal(patient, email);
    } else {
      console.log('Patient not found, showing error message');
      setInlineMsg('err', '❌ Patient not found in system.');
    }
  }

  function showPatientConfirmationModal(patient, email) {
    console.log('showPatientConfirmationModal called with:', patient, email);
    // Update the confirmation modal with patient data
    const fullNameEl = document.getElementById('patientFullName');
    const emailEl = document.getElementById('confirmationEmail');
    const patientCodeEl = document.getElementById('confirmationPatientCode');
    const statusEl = document.getElementById('verificationStatus');
    
    console.log('Elements found:', {fullNameEl, emailEl, patientCodeEl, statusEl});
    
    if(fullNameEl) fullNameEl.textContent = patient.full_name || 'N/A';
    if(emailEl) emailEl.textContent = patient.email || email;
    if(patientCodeEl) patientCodeEl.textContent = patient.patient_code || 'N/A';
    if(statusEl) {
      statusEl.textContent = 'Verified';
      statusEl.className = 'fw-semibold text-success';
    }
    
    // Handle profile photo
    const profilePhotoDiv = document.getElementById('patientProfilePhoto');
    if (profilePhotoDiv) {
      if (patient.profile_photo_url) {
        profilePhotoDiv.innerHTML = `
          <img src="${patient.profile_photo_url}" 
               class="rounded-circle" 
               style="width: 80px; height: 80px; object-fit: cover; border: 3px solid #28a745;" 
               alt="Profile Photo">
        `;
      } else {
        profilePhotoDiv.innerHTML = `
          <div class="rounded-circle bg-light d-flex align-items-center justify-content-center mx-auto" 
               style="width: 80px; height: 80px; border: 3px solid #28a745;">
            <i class="bi bi-person-fill text-muted" style="font-size: 2.5rem;"></i>
          </div>
        `;
      }
    }
    
    // Enable the proceed button
    const proceedBtn = document.getElementById('qrConfirmProceed');
    console.log('Proceed button found:', proceedBtn);
    if (proceedBtn) {
      proceedBtn.disabled = false;
      proceedBtn.innerHTML = '<i class="bi bi-check-circle me-1"></i>Proceed';
    }
    
    // Show the confirmation modal
    const modalElement = document.getElementById('qrConfirmationModal');
    console.log('Modal element found:', modalElement);
    if (modalElement) {
      const confirmationModal = new bootstrap.Modal(modalElement);
      console.log('Showing confirmation modal');
      confirmationModal.show();
    } else {
      console.error('qrConfirmationModal element not found!');
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
    html5Qr.start(camId, { fps:2 }, onScanSuccess, onScanFailure)
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
  document.getElementById('qrEmailGo')?.addEventListener('click', async function(){
    const v = (document.getElementById('qrEmailFallback')||{}).value || '';
    if(!v.trim()) {
      setInlineMsg('err', 'Please enter an email address.');
      return;
    }
    if(qrModal) qrModal.hide();
    await handleReceptionEmail(v);
  });

  // Refresh camera
  document.getElementById('refreshCameraBtn')?.addEventListener('click', function(){
    Html5Qrcode.getCameras().then(cams=>{
      const id = (cams && cams[0] && cams[0].id) || undefined;
      startScanner(id);
    }).catch(()=> startScanner());
  });

  // Confirmation modal buttons
  document.getElementById('qrConfirmProceed')?.addEventListener('click', function(){
    const m = bootstrap.Modal.getInstance(document.getElementById('qrConfirmationModal'));
    if(m) m.hide();
    
    // Get the patient email from the confirmation modal
    const patientEmail = document.getElementById('confirmationEmail')?.textContent;
    const patientCode = document.getElementById('confirmationPatientCode')?.textContent;
    
    console.log('Proceed clicked - Patient Email:', patientEmail, 'Patient Code:', patientCode);
    
    if(patientEmail) {
      // Navigate to reception dashboard with patient email parameter
      console.log('Redirecting to reception dashboard with patient email');
      window.location.href = `/dashboard/reception/?patient_email=${encodeURIComponent(patientEmail)}`;
    } else if(patientCode) {
      // Fallback to patient search
      console.log('Fallback to patient search with patient code');
      window.location.href = `/patients/?search=${encodeURIComponent(patientCode)}`;
    } else {
      console.error('No patient email or code found for redirection');
    }
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


