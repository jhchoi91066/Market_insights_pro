// main.js
document.addEventListener('DOMContentLoaded', (event) => {
    const analysisForm = document.getElementById('analysisForm');
    const mainContent = document.getElementById('mainContent');
    const loader = document.getElementById('loader');
    let isSubmitting = false; // 중복 제출 방지

    if (analysisForm) {
        analysisForm.addEventListener('submit', (e) => {
            // 중복 제출 방지
            if (isSubmitting) {
                e.preventDefault();
                alert('⏳ Analysis is already in progress. Please wait...\n\nNote: Only one analysis can run at a time to ensure accurate results.');
                return false;
            }

            isSubmitting = true;
            
            // 폼 제출 시, 메인 컨텐츠를 숨기고 로더를 표시
            if(mainContent && loader) {
                mainContent.classList.add('d-none'); // d-none은 bootstrap에서 display: none;을 의미
                loader.classList.remove('d-none');
            }

            // 제출 버튼 비활성화
            const submitButton = analysisForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '⏳ Analyzing... (1-2 minutes)';
            }
        });
    }
});