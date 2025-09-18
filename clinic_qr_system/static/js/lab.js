(function(){
  // Ensure consistent event binding and behavior across reloads
  const form = document.querySelector('form');
  if(!form) return;
  const labTypeSel = form.querySelector('select[name="lab_type"]');
  if(labTypeSel){
    labTypeSel.classList.add('form-select');
  }
  // Normalize all dynamic fields to form-control
  const inputs = form.querySelectorAll('input[type="text"], input[type="number"], textarea');
  inputs.forEach(el=> el.classList.add('form-control'));
})();


