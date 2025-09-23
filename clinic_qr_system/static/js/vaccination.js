// Vaccination System JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeVaccinationSystem();
});

function initializeVaccinationSystem() {
    initializePatientSearch();
    initializeSchedulePreviews();
    initializeFormValidations();
    initializeBulkOperations();
}

// Patient Search Functionality
function initializePatientSearch() {
    const patientSearchInputs = document.querySelectorAll('#patient-search');
    
    patientSearchInputs.forEach(input => {
        let timeout;
        
        input.addEventListener('input', function() {
            clearTimeout(timeout);
            const query = this.value.trim();
            
            if (query.length >= 2) {
                timeout = setTimeout(() => {
                    searchPatients(query, this);
                }, 300);
            } else {
                clearPatientSearchResults(this);
            }
        });
    });
}

function searchPatients(query, inputElement) {
    fetch(`/vaccinations/ajax/search-patients/?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            displayPatientSearchResults(data.results, inputElement);
        })
        .catch(error => {
            console.error('Error searching patients:', error);
        });
}

function displayPatientSearchResults(patients, inputElement) {
    clearPatientSearchResults(inputElement);
    
    if (patients.length === 0) {
        return;
    }
    
    const resultsContainer = document.createElement('div');
    resultsContainer.className = 'patient-search-results position-absolute bg-white border rounded shadow-sm';
    resultsContainer.style.cssText = 'top: 100%; left: 0; right: 0; z-index: 1000; max-height: 200px; overflow-y: auto;';
    
    patients.forEach(patient => {
        const resultItem = document.createElement('div');
        resultItem.className = 'patient-result-item p-2 border-bottom cursor-pointer';
        resultItem.style.cursor = 'pointer';
        resultItem.innerHTML = `
            <div class="fw-bold">${patient.name}</div>
            <small class="text-muted">${patient.code} • ${patient.email}</small>
        `;
        
        resultItem.addEventListener('click', function() {
            selectPatient(patient, inputElement);
        });
        
        resultsContainer.appendChild(resultItem);
    });
    
    inputElement.parentNode.style.position = 'relative';
    inputElement.parentNode.appendChild(resultsContainer);
}

function clearPatientSearchResults(inputElement) {
    const existingResults = inputElement.parentNode.querySelector('.patient-search-results');
    if (existingResults) {
        existingResults.remove();
    }
}

function selectPatient(patient, inputElement) {
    inputElement.value = patient.name;
    clearPatientSearchResults(inputElement);
    inputElement.dispatchEvent(new Event('change'));
}

// Vaccine Schedule Preview Functionality
function initializeSchedulePreviews() {
    const vaccineTypeSelects = document.querySelectorAll('select[name="vaccine_type"]');
    const startDateInputs = document.querySelectorAll('input[name="start_date"]');
    
    vaccineTypeSelects.forEach(select => {
        select.addEventListener('change', updateSchedulePreview);
    });
    
    startDateInputs.forEach(input => {
        input.addEventListener('change', updateSchedulePreview);
    });
}

function updateSchedulePreview() {
    const vaccineTypeSelect = document.querySelector('select[name="vaccine_type"]');
    const startDateInput = document.querySelector('input[name="start_date"]');
    const schedulePreview = document.querySelector('#schedule-text');
    
    if (!vaccineTypeSelect || !startDateInput || !schedulePreview) {
        return;
    }
    
    const vaccineId = vaccineTypeSelect.value;
    const startDate = startDateInput.value;
    
    if (vaccineId && startDate) {
        fetch(`/vaccinations/ajax/vaccine-schedule/?vaccine_id=${vaccineId}&start_date=${startDate}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const schedule = data.schedule.map(date => new Date(date).toLocaleDateString());
                    schedulePreview.textContent = schedule.join(' → ');
                } else {
                    schedulePreview.textContent = 'Unable to load schedule';
                }
            })
            .catch(error => {
                console.error('Error loading schedule:', error);
                schedulePreview.textContent = 'Error loading schedule';
            });
    } else {
        schedulePreview.textContent = 'Select a vaccine type and start date to see the schedule';
    }
}

// Form Validation Functionality
function initializeFormValidations() {
    const doseIntervalsInputs = document.querySelectorAll('input[name="dose_intervals"]');
    
    doseIntervalsInputs.forEach(input => {
        input.addEventListener('input', validateDoseIntervals);
    });
    
    const dateInputs = document.querySelectorAll('input[type="date"]');
    
    dateInputs.forEach(input => {
        input.addEventListener('change', validateDateInput);
    });
}

function validateDoseIntervals(e) {
    const input = e.target;
    const value = input.value.trim();
    
    if (value === '') {
        input.setCustomValidity('');
        return;
    }
    
    const intervals = value.split(',').map(x => parseInt(x.trim()));
    
    if (intervals.some(x => isNaN(x) || x < 0)) {
        input.setCustomValidity('Please enter valid positive numbers separated by commas');
    } else {
        input.setCustomValidity('');
    }
}

function validateDateInput(e) {
    const input = e.target;
    const value = input.value;
    const today = new Date().toISOString().split('T')[0];
    
    if (input.name === 'start_date' || input.name === 'administered_date') {
        if (value > today) {
            input.setCustomValidity('Date cannot be in the future');
        } else {
            input.setCustomValidity('');
        }
    } else if (input.name === 'expiry_date') {
        if (value <= today) {
            input.setCustomValidity('Expiry date must be in the future');
        } else {
            input.setCustomValidity('');
        }
    }
}

// Bulk Operations Functionality
function initializeBulkOperations() {
    const selectAllCheckboxes = document.querySelectorAll('#select-all');
    const patientCheckboxes = document.querySelectorAll('input[name="patients"]');
    
    selectAllCheckboxes.forEach(selectAll => {
        selectAll.addEventListener('change', function() {
            patientCheckboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
    });
    
    patientCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const checkedCount = document.querySelectorAll('input[name="patients"]:checked').length;
            const selectAll = document.querySelector('#select-all');
            
            if (selectAll) {
                selectAll.checked = checkedCount === patientCheckboxes.length;
                selectAll.indeterminate = checkedCount > 0 && checkedCount < patientCheckboxes.length;
            }
        });
    });
}