/**
 * Proovexa Plagiarism Report Asynchronous Poller
 *
 * Implements exponential backoff polling to eliminate race conditions where
 * reports trigger before similarity indexing and match computation finish.
 *
 * Guarantees that reports are only displayed or downloaded when:
 *  - status === 'COMPLETE' or status === 'READY'
 *  - similarity_ready === true
 * Never accepts preliminary 0% scores while status is 'PROCESSING' or 'QUEUED'.
 */

(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.ReportPoller = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    /**
     * Sleep helper for async/await.
     * @param {number} ms
     * @returns {Promise<void>}
     */
    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    /**
     * Poll a status endpoint until analysis is complete.
     *
     * @param {string} statusUrl - The status URL (e.g. '/analysis/<doc_id>/status/' or '/reports/<report_id>/status/')
     * @param {Object} [options] - Polling configuration
     * @param {number} [options.maxRetries=15] - Maximum retry attempts
     * @param {number} [options.initialDelayMs=1000] - Initial delay in milliseconds
     * @param {number} [options.backoffFactor=1.5] - Multiplier for each subsequent retry
     * @param {number} [options.maxDelayMs=5000] - Maximum delay ceiling between attempts
     * @param {Function} [options.onProgress] - Callback invoked on each polling tick: (statusData, attempt) => void
     * @returns {Promise<Object>} Resolves with the finalized report status payload
     */
    async function getCompletedReport(statusUrl, options) {
        var opts = options || {};
        var maxRetries = typeof opts.maxRetries === 'number' ? opts.maxRetries : 15;
        var delay = typeof opts.initialDelayMs === 'number' ? opts.initialDelayMs : 1000;
        var backoffFactor = typeof opts.backoffFactor === 'number' ? opts.backoffFactor : 1.5;
        var maxDelay = typeof opts.maxDelayMs === 'number' ? opts.maxDelayMs : 5000;
        var onProgress = typeof opts.onProgress === 'function' ? opts.onProgress : null;

        var attempts = 0;

        while (attempts < maxRetries) {
            var response;
            try {
                response = await fetch(statusUrl, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    credentials: 'same-origin'
                });
            } catch (networkErr) {
                // Network glitch; retry if attempts remain
                attempts++;
                if (attempts >= maxRetries) {
                    throw new Error('Network error while polling plagiarism status: ' + networkErr.message);
                }
                await sleep(delay);
                delay = Math.min(maxDelay, delay * backoffFactor);
                continue;
            }

            if (!response.ok && response.status !== 425) {
                // If 403, 404, or 500, throw immediately
                throw new Error('Status check failed with HTTP ' + response.status + ': ' + response.statusText);
            }

            var data = {};
            try {
                data = await response.json();
            } catch (parseErr) {
                data = {};
            }

            if (onProgress) {
                try {
                    onProgress(data, attempts + 1);
                } catch (cbErr) {
                    console.warn('[ReportPoller] onProgress callback threw:', cbErr);
                }
            }

            // Normalization of status strings
            var rawStatus = (data.status || data.report_status || data.document_status || '').toUpperCase();
            var isSimilarityReady = Boolean(data.similarity_ready || data.is_ready || data.can_render_report);

            // 1. Check for COMPLETE or READY
            if (rawStatus === 'COMPLETE' || rawStatus === 'READY' || isSimilarityReady) {
                // Double check that similarity_ready is true and not preliminary
                return data;
            }

            // 2. Check for FAILED or ERROR
            if (rawStatus === 'FAILED' || rawStatus === 'ERROR') {
                var errorMsg = data.error_message || data.error || 'Plagiarism analysis failed.';
                throw new Error('Plagiarism analysis failed: ' + errorMsg);
            }

            // 3. Status is PROCESSING or QUEUED: do NOT generate or render report yet
            await sleep(delay);
            delay = Math.min(maxDelay, delay * backoffFactor);
            attempts++;
        }

        throw new Error('Plagiarism analysis timed out after ' + maxRetries + ' attempts. Please refresh or try again later.');
    }

    /**
     * Poll until ready, then automatically redirect to report URL or trigger download.
     *
     * @param {string} statusUrl
     * @param {string} fallbackRedirectUrl
     * @param {Object} [options]
     */
    async function pollAndRedirect(statusUrl, fallbackRedirectUrl, options) {
        var data = await getCompletedReport(statusUrl, options);
        var target = (data && (data.report_url || data.pdf_url)) || fallbackRedirectUrl;
        if (target) {
            window.location.href = target;
        }
        return data;
    }

    return {
        getCompletedReport: getCompletedReport,
        pollAndRedirect: pollAndRedirect,
        sleep: sleep
    };
}));
