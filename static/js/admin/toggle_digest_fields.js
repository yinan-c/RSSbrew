document.addEventListener('DOMContentLoaded', function() {
    var toggleDigestCheckbox = document.querySelector('#id_toggle_digest');
    var digestFields = document.querySelectorAll('.field-digest_frequency, .field-last_digest, .field-include_one_line_summary, .field-include_summary, .field-include_content, .field-use_ai_digest, .field-include_toc');

    function toggleDigestFields() {
        digestFields.forEach(function(field) {
            field.style.display = toggleDigestCheckbox.checked ? 'block' : 'none';
        });
    }

    toggleDigestCheckbox.addEventListener('change', toggleDigestFields);
    toggleDigestFields();  // Call on initial load
});