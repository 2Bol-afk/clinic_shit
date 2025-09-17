(function(){
  // Dynamic vaccination form enhancements
  const select = document.querySelector('select[name="vaccine_type"]');
  if(!select) return;
  const container = document.getElementById('vaccDynFields') || document;
  const fieldLabels = {
    'COVID-19 Vaccine': [['brand','Vaccine Brand'],['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Influenza (Flu) Vaccine': [['brand','Vaccine Brand'],['strain','Yearly Strain/Type'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Hepatitis B Vaccine': [['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Tetanus Vaccine': [['vaccine_type','Vaccine Type'],['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Measles, Mumps, Rubella (MMR) Vaccine': [['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Polio Vaccine': [['vaccine_type','Vaccine Type (OPV/IPV)'],['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection (if injectable)'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Varicella (Chickenpox) Vaccine': [['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']],
    'Human Papillomavirus (HPV) Vaccine': [['brand','Vaccine Brand'],['dose_number','Dose Number'],['batch','Batch/Lot Number'],['expiry','Expiry Date'],['site','Site of Injection'],['date_admin','Date of Administration'],['admin_by','Administered By'],['remarks','Remarks']]
  };
  function syncLabels(){
    const vt = select.value;
    const config = fieldLabels[vt] || [];
    // hide all unknown fields; show only in config
    const fields = container.querySelectorAll('.col-md-6');
    fields.forEach(div=>{
      const input = div.querySelector('input, textarea, select');
      if(!input) return;
      const name = input.getAttribute('name');
      const item = config.find(([n])=> n===name);
      if(item){
        div.style.display = '';
        const label = div.querySelector('label');
        if(label) label.textContent = item[1];
      } else if(name !== 'vaccine_type') {
        div.style.display = 'none';
      }
    });
  }
  select.addEventListener('change', syncLabels);
  // initial
  setTimeout(syncLabels, 0);
})();


