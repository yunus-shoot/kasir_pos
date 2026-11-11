(() => {
    function uppercaseInput(input) {
        const start = input.selectionStart;
        const end = input.selectionEnd;
        const value = input.value;
        const uppercaseValue = value.toLocaleUpperCase('id-ID');
        if (value === uppercaseValue) return;

        input.value = uppercaseValue;
        if (start !== null && end !== null) {
            const nextStart = value.slice(0, start).toLocaleUpperCase('id-ID').length;
            const nextEnd = value.slice(0, end).toLocaleUpperCase('id-ID').length;
            input.setSelectionRange(nextStart, nextEnd);
        }
    }

    document.querySelectorAll('[data-auto-uppercase]').forEach(input => {
        input.addEventListener('input', event => {
            if (!event.isComposing) uppercaseInput(input);
        });
        input.addEventListener('compositionend', () => uppercaseInput(input));
    });

    function groupDigits(digits) {
        return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    function formatValue(value, initial = false) {
        let raw = String(value || '').trim();
        if (!raw) return '';

        let integerPart = raw;
        let fractionPart = '';
        let hasDecimal = false;

        if (initial && !raw.includes(',') && raw.includes('.')) {
            const decimalIndex = raw.lastIndexOf('.');
            const possibleFraction = raw.slice(decimalIndex + 1);
            if (possibleFraction.length > 0 && possibleFraction.length <= 2) {
                integerPart = raw.slice(0, decimalIndex);
                fractionPart = possibleFraction.replace(/\D/g, '').slice(0, 2);
                hasDecimal = fractionPart.length > 0 && /[1-9]/.test(fractionPart);
            }
        } else if (raw.includes(',')) {
            const decimalIndex = raw.indexOf(',');
            integerPart = raw.slice(0, decimalIndex);
            fractionPart = raw.slice(decimalIndex + 1).replace(/\D/g, '').slice(0, 2);
            hasDecimal = true;
        }

        const digits = integerPart.replace(/\D/g, '');
        const grouped = groupDigits(digits || (raw.endsWith(',') ? '0' : ''));
        return grouped + (hasDecimal ? `,${fractionPart}` : raw.endsWith(',') ? ',' : '');
    }

    function toStandardValue(value) {
        return String(value || '').replace(/\./g, '').replace(',', '.');
    }

    function positionForDigitCount(value, digitCount) {
        if (digitCount === 0) return 0;
        let digitsSeen = 0;
        for (let index = 0; index < value.length; index += 1) {
            if (/\d/.test(value[index])) digitsSeen += 1;
            if (digitsSeen === digitCount) return index + 1;
        }
        return value.length;
    }

    function initializeIndonesianInputFields() {
        document.querySelectorAll('[data-indonesian-number]:not([data-number-init])').forEach(input => {
            input.dataset.numberInit = 'true';

            const fieldName = input.name;
            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = fieldName;
            hidden.value = toStandardValue(input.value);
            input.name = '';
            input.insertAdjacentElement('afterend', hidden);

            input.value = formatValue(input.value, true);
            hidden.value = toStandardValue(input.value);

            input.addEventListener('input', () => {
                const digitCount = (input.value.slice(0, input.selectionStart).match(/\d/g) || []).length;
                input.value = formatValue(input.value);
                input.setSelectionRange(positionForDigitCount(input.value, digitCount), positionForDigitCount(input.value, digitCount));
                hidden.value = toStandardValue(input.value);
            });

            input.form?.addEventListener('submit', () => {
                hidden.value = toStandardValue(input.value);
            }, true);
        });
    }

    initializeIndonesianInputFields();

    const observer = new MutationObserver(() => {
        initializeIndonesianInputFields();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    window.parseIndonesianNumber = value => Number(toStandardValue(value)) || 0;
})();