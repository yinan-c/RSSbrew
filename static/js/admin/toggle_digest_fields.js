document.addEventListener('DOMContentLoaded', function() {
    var toggleDigestCheckbox = document.querySelector('#id_toggle_digest');
    var digestFrequencyFields = document.querySelectorAll('.field-digest_frequency, .field-last_digest');

    // Find the "What to include in digest" fieldset by looking for the fieldset containing include_toc
    var allFieldsets = document.querySelectorAll('fieldset');
    var digestContentFieldset = null;

    allFieldsets.forEach(function(fieldset) {
        if (fieldset.querySelector('.field-include_toc')) {
            digestContentFieldset = fieldset;
        }
    });

    function toggleDigestFields() {
        // Toggle digest frequency fields
        digestFrequencyFields.forEach(function(field) {
            field.style.display = toggleDigestCheckbox.checked ? 'block' : 'none';
        });

        // Toggle entire "What to include in digest" fieldset
        if (digestContentFieldset) {
            digestContentFieldset.style.display = toggleDigestCheckbox.checked ? 'block' : 'none';
        }
    }

    toggleDigestCheckbox.addEventListener('change', toggleDigestFields);
    toggleDigestFields();  // Call on initial load
});
