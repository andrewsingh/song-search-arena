/**
 * Genre Selection Page
 * Handles client-side validation for genre selection
 */

(function() {
    'use strict';

    const form = document.getElementById('genre-form');
    const checkboxes = document.querySelectorAll('input[name="genres"]');
    const validationError = document.getElementById('validation-error');
    const submitButton = form.querySelector('button[type="submit"]');

    /**
     * Check if at least one genre is selected
     */
    function validateSelection() {
        const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
        return checkedCount > 0;
    }

    /**
     * Update UI based on validation state
     */
    function updateUI() {
        const isValid = validateSelection();

        if (!isValid) {
            validationError.style.display = 'block';
            submitButton.disabled = true;
        } else {
            validationError.style.display = 'none';
            submitButton.disabled = false;
        }
    }

    /**
     * Handle form submission
     */
    function handleSubmit(e) {
        if (!validateSelection()) {
            e.preventDefault();
            validationError.style.display = 'block';
            submitButton.disabled = true;
            return false;
        }
        return true;
    }

    // Attach event listeners to checkboxes
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', updateUI);
    });

    // Attach form submit handler
    form.addEventListener('submit', handleSubmit);

    // Initial UI update
    updateUI();
})();
