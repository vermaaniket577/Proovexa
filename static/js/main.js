/**
 * ScholarGuard - Main JavaScript
 */
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle
    const sidebar = document.getElementById('sidebar');
    const sidebarOpen = document.getElementById('sidebarOpen');
    const sidebarClose = document.getElementById('sidebarClose');

    if (sidebarOpen) {
        sidebarOpen.addEventListener('click', () => sidebar.classList.add('show'));
    }
    if (sidebarClose) {
        sidebarClose.addEventListener('click', () => sidebar.classList.remove('show'));
    }

    // Close sidebar on overlay click (mobile)
    document.addEventListener('click', function(e) {
        if (sidebar && sidebar.classList.contains('show') &&
            !sidebar.contains(e.target) && e.target !== sidebarOpen) {
            sidebar.classList.remove('show');
        }
    });

    // Drag and drop upload
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('doc-file');

    if (uploadZone && fileInput) {
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                uploadZone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                uploadZone.classList.remove('drag-over');
            });
        });

        uploadZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                updateFileDisplay(files[0]);
            }
        });

        uploadZone.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                updateFileDisplay(this.files[0]);
            }
        });
    }

    function updateFileDisplay(file) {
        const zone = document.getElementById('upload-zone');
        if (!zone) return;

        const sizeKB = (file.size / 1024).toFixed(1);
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        const sizeStr = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
        const ext = file.name.split('.').pop().toLowerCase();

        const colorMap = { pdf: '#ef4444', docx: '#3b82f6', txt: '#6b7280', pptx: '#f59e0b' };
        const color = colorMap[ext] || '#6b7280';

        zone.innerHTML = `
            <div class="file-type-badge ${ext}" style="margin: 0 auto 12px; width: 48px; height: 48px; font-size: 0.85rem;">
                ${ext}
            </div>
            <div class="upload-title">${file.name}</div>
            <div class="upload-subtitle">${sizeStr} • Click or drag to change</div>
        `;

        // Auto-fill title if empty
        const titleInput = document.getElementById('doc-title');
        if (titleInput && !titleInput.value) {
            const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
            titleInput.value = nameWithoutExt.replace(/[_-]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        }
    }

    // Auto-dismiss alerts
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 8000);
    });

    // Fade-in animations
    document.querySelectorAll('.fade-in-item').forEach((el, index) => {
        el.style.animationDelay = `${index * 0.05}s`;
        el.classList.add('fade-in');
    });

    // Form validation styling
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                form.classList.add('was-validated');
            } else {
                // Show loading state on submit button
                const submitBtn = form.querySelector('[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
                }
            }
        });
    });

    // Tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

    // Ctrl+K to focus global search
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            const searchInput = document.getElementById('globalSearchInput');
            if (searchInput) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        }
    });
});

