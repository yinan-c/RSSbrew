document.addEventListener('DOMContentLoaded', function() {
    var toggleDigestCheckbox = document.querySelector('#id_use_ai_digest');
    var digestFields = document.querySelectorAll('.field-additional_prompt_for_digest, .field-send_full_article, .field-digest_model, .field-other_digest_model');

    function toggleDigestFields() {
        digestFields.forEach(function(field) {
            field.style.display = toggleDigestCheckbox.checked ? 'block' : 'none';
        });
    }

    toggleDigestCheckbox.addEventListener('change', toggleDigestFields);
    toggleDigestFields();  // Call on initial load
});