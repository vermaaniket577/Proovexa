/**
 * ScholarGuard / Proovexa - Main JavaScript & Academic Loader System
 */

// ----------------------------------------------------------------------------
// 1. Slim Page-Top Progress Bar Controller
// ----------------------------------------------------------------------------
const PageTopLoader = (function() {
    let el = null;
    let timer = null;
    let progress = 0;

    function getElement() {
        if (!el) {
            el = document.getElementById('page-top-loader');
            if (!el) {
                el = document.createElement('div');
                el.id = 'page-top-loader';
                el.className = 'page-top-loader';
                document.body.appendChild(el);
            }
        }
        return el;
    }

    return {
        start: function() {
            const bar = getElement();
            if (!bar) return;
            clearInterval(timer);
            progress = 10;
            bar.classList.add('active');
            bar.style.width = '10%';
            bar.style.opacity = '1';

            timer = setInterval(function() {
                if (progress < 85) {
                    progress += Math.random() * 12;
                    bar.style.width = Math.min(progress, 88) + '%';
                }
            }, 250);
        },
        done: function() {
            const bar = getElement();
            if (!bar) return;
            clearInterval(timer);
            bar.style.width = '100%';
            setTimeout(function() {
                bar.style.opacity = '0';
                setTimeout(function() {
                    bar.classList.remove('active');
                    bar.style.width = '0%';
                }, 400);
            }, 200);
        }
    };
})();

// ----------------------------------------------------------------------------
// 2. Global Full-Screen Academic Glassmorphism Overlay Loader
// ----------------------------------------------------------------------------
const GlobalAppLoader = (function() {
    let el = null;
    let headingEl = null;
    let subheadingEl = null;
    let intervalTimer = null;

    const defaultAcademicSteps = [
        "Extracting clean text & normalizing academic sentences...",
        "Searching Google Scholar, Shodhganga & ShodhGangotri...",
        "Crawling candidate research publications 1-by-1...",
        "Executing Winnowing fingerprinting & line-by-line matching...",
        "Analyzing AI writing probability & perplexity metrics...",
        "Generating Turnitin-compliant originality breakdown..."
    ];

    function getElements() {
        if (!el) {
            el = document.getElementById('global-app-loader');
            if (el) {
                headingEl = document.getElementById('loader-heading');
                subheadingEl = document.getElementById('loader-subheading');
            }
        }
        return el;
    }

    return {
        show: function(title, subtitle, dynamicSteps) {
            const loader = getElements();
            if (!loader) return;

            if (headingEl) {
                headingEl.innerText = title || "Analyzing Academic Integrity";
            }
            if (subheadingEl) {
                subheadingEl.innerText = subtitle || defaultAcademicSteps[0];
            }

            // Cycle through reassuring academic workflow messages
            const steps = Array.isArray(dynamicSteps) && dynamicSteps.length > 0 ? dynamicSteps : defaultAcademicSteps;
            let stepIndex = 0;
            clearInterval(intervalTimer);
            intervalTimer = setInterval(function() {
                stepIndex = (stepIndex + 1) % steps.length;
                if (subheadingEl) {
                    subheadingEl.style.opacity = '0';
                    setTimeout(function() {
                        subheadingEl.innerText = steps[stepIndex];
                        subheadingEl.style.opacity = '1';
                    }, 200);
                }
            }, 3000);

            loader.classList.remove('d-none');
            // Trigger transition next frame
            requestAnimationFrame(function() {
                loader.classList.add('show');
            });
            PageTopLoader.start();
        },
        hide: function() {
            clearInterval(intervalTimer);
            const loader = getElements();
            if (loader) {
                loader.classList.remove('show');
                setTimeout(function() {
                    loader.classList.add('d-none');
                }, 350);
            }
            PageTopLoader.done();
        }
    };
})();

// Expose on window
window.PageTopLoader = PageTopLoader;
window.GlobalAppLoader = GlobalAppLoader;
window.showLoader = function(title, subtitle, steps) {
    GlobalAppLoader.show(title, subtitle, steps);
};
window.hideLoader = function() {
    GlobalAppLoader.hide();
};

// ----------------------------------------------------------------------------
// 3. Main DOM Initialization & Event Handlers
// ----------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    // Complete top progress loader if it was active
    PageTopLoader.done();

    // Prevent stuck loader when navigating back via browser history
    window.addEventListener('pageshow', function() {
        GlobalAppLoader.hide();
        PageTopLoader.done();
    });

    // Sidebar toggle
    const sidebar = document.getElementById('sidebar');
    const sidebarOpen = document.getElementById('sidebarOpen');
    const sidebarClose = document.getElementById('sidebarClose');

    if (sidebarOpen && sidebar) {
        sidebarOpen.addEventListener('click', () => sidebar.classList.add('show'));
    }
    if (sidebarClose && sidebar) {
        sidebarClose.addEventListener('click', () => sidebar.classList.remove('show'));
    }

    // Close sidebar on overlay click (mobile)
    document.addEventListener('click', function(e) {
        if (sidebar && sidebar.classList.contains('show') &&
            !sidebar.contains(e.target) && e.target !== sidebarOpen) {
            sidebar.classList.remove('show');
        }
    });

    // Drag and drop upload handler
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('doc-file') || document.querySelector('input[type="file"]');

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
        const titleInput = document.getElementById('doc-title') || document.querySelector('input[name="title"]');
        if (titleInput && !titleInput.value) {
            const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
            titleInput.value = nameWithoutExt.replace(/[_-]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        }
    }

    // Auto-dismiss alert banners
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            if (typeof bootstrap !== 'undefined' && bootstrap.Alert) {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }
        }, 8000);
    });

    // Form submission loaders
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                form.classList.add('was-validated');
                return;
            }

            const isUpload = form.id === 'upload-form' || form.enctype === 'multipart/form-data';
            const submitBtn = form.querySelector('[type="submit"]');

            if (submitBtn) {
                submitBtn.disabled = true;
                const originalText = submitBtn.innerText.trim();
                submitBtn.setAttribute('data-original-text', originalText);
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
            }

            if (isUpload) {
                GlobalAppLoader.show(
                    "Uploading & Extracting Document",
                    "Validating document format, sanitizing text, and preparing for similarity indexing...",
                    [
                        "Uploading document securely to private storage...",
                        "Extracting high-fidelity academic text & paragraphs...",
                        "Sanitizing characters and computing token hashes...",
                        "Preparing multi-repository search index..."
                    ]
                );
            } else {
                PageTopLoader.start();
            }
        });
    });

    // Analysis button / link loaders (e.g. Quick Scan, Run Analysis)
    document.querySelectorAll('a[href*="quick_scan"], a[href*="analysis/run"], .btn-run-analysis').forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (btn.getAttribute('target') === '_blank') return;
            GlobalAppLoader.show(
                "Analyzing Academic Integrity",
                "Searching Google Scholar, Shodhganga & ShodhGangotri...",
                [
                    "Searching Google Scholar, Shodhganga & ShodhGangotri...",
                    "Crawling candidate Indian theses and research publications...",
                    "Executing Winnowing fingerprinting & line-by-line matching...",
                    "Analyzing Turnitin AI writing probability & perplexity...",
                    "Generating interactive multi-color originality report..."
                ]
            );
        });
    });

    // PDF Export / Download button loaders
    document.querySelectorAll('a[href*="pdf"], a[download], .btn-download-pdf').forEach(btn => {
        btn.addEventListener('click', function(e) {
            PageTopLoader.start();
            setTimeout(function() {
                PageTopLoader.done();
            }, 3000);
        });
    });

    // Intercept standard internal links for smooth top progress bar
    document.querySelectorAll('a[href]').forEach(link => {
        link.addEventListener('click', function(e) {
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:') ||
                href.startsWith('mailto:') || href.startsWith('tel:') ||
                link.getAttribute('target') === '_blank' ||
                link.getAttribute('data-bs-toggle') ||
                e.ctrlKey || e.metaKey || e.shiftKey) {
                return;
            }
            PageTopLoader.start();
        });
    });

    // Tooltips initialization
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
    }

    // Ctrl+K global search focus
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
