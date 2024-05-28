document.addEventListener('DOMContentLoaded', function() {
    var toggleDigestCheckbox = document.querySelector('#id_toggle_digest');
    var digestFields = document.querySelectorAll('.field-digest_frequency, .field-digest_time, .field-additional_prompt_for_digest, .field-send_full_article');

    function toggleDigestFields() {
        digestFields.forEach(function(field) {
            field.style.display = toggleDigestCheckbox.checked ? 'block' : 'none';
        });
    }

    toggleDigestCheckbox.addEventListener('change', toggleDigestFields);
    toggleDigestFields();  // Call on initial load
});