document.addEventListener('DOMContentLoaded', function () {
    // DOM Elements
    const syftUrlInput = document.getElementById('syft-url');
    const serverUrlInput = document.getElementById('server-url');
    const fromEmailInput = document.getElementById('from-email');
    const toEmailInput = document.getElementById('to-email');
    const appNameInput = document.getElementById('app-name');
    const appEndpointInput = document.getElementById('app-endpoint');
    const autoResumeCheckbox = document.getElementById('auto-resume');

    const testConnectionBtn = document.getElementById('test-connection');
    const validateUrlBtn = document.getElementById('validate-url');
    const resetDefaultsBtn = document.getElementById('reset-defaults');

    const headersList = document.getElementById('headers-list');
    const addHeaderBtn = document.getElementById('add-header');

    const requestBodyTextarea = document.getElementById('request-body');
    const formatJsonBtn = document.getElementById('format-json');

    const sendRequestBtn = document.getElementById('send-request');

    const requestsList = document.getElementById('requests-list');
    const requestDetails = document.getElementById('request-details');
    const clearRequestsBtn = document.getElementById('clear-requests');

    const toast = document.getElementById('toast');

    // Debug mode for detailed logging
    const DEBUG = false;

    // Currently selected request ID
    let activeRequestId = null;

    // App State with defaults
    const defaultState = window.defaultState
    console.log("defaultState", defaultState)

    function initDefaults() {
        // Load current state from localStorage
        const savedState = JSON.parse(localStorage.getItem('syftBoxRpcState')) || {};

        // Set values in the input fields, using saved state if available, otherwise default
        document.getElementById('server-url').value = savedState.serverUrl || defaultState.serverUrl;
        document.getElementById('from-email').value = savedState.fromEmail || defaultState.fromEmail;
        document.getElementById('to-email').value = savedState.toEmail || defaultState.toEmail;
        document.getElementById('app-name').value = savedState.appName || defaultState.appName;
        document.getElementById('app-endpoint').value = savedState.appEndpoint || defaultState.appEndpoint;
        document.getElementById('auto-resume').checked = savedState.autoResume !== undefined ? savedState.autoResume : defaultState.autoResume;
    }

    // Initialize defaults on page load
    initDefaults();

    let appState = { ...defaultState };

    // Storage key
    const STORAGE_KEY = 'syftBoxRpcState';

    // ==========================================
    // Helper Functions
    // ==========================================

    /**
     * Show a toast notification
     * @param {string} message - The message to show
     * @param {string} type - The type of toast (info, success, error)
     */
    function showToast(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);

        toast.textContent = message;
        toast.className = `toast toast-${type} show`;

        setTimeout(() => {
            toast.className = 'toast';
        }, 3000);
    }

    /**
     * Builds a syft URL from the current state
     * @returns {string} The constructed syft URL
     */
    function buildSyftUrl() {
        if (!appState.toEmail || !appState.appName || !appState.appEndpoint) {
            return '';
        }

        const [username, domain] = appState.toEmail.split('@');
        if (!username || !domain) {
            return '';
        }

        let endpoint = appState.appEndpoint;

        // Remove leading slash if present
        if (endpoint.startsWith('/')) {
            endpoint = endpoint.substring(1);
        }

        return `syft://${username}@${domain}/app_data/${appState.appName}/rpc/${endpoint}`;
    }

    /**
     * Parse a syft URL to extract components
     * @param {string} syftUrl - The syft URL to parse
     * @returns {object|null} The parsed components or null if invalid
     */
    function parseSyftUrl(syftUrl) {
        try {
            const parsedUrl = new SyftBoxSDK().parseSyftUrl(syftUrl);
            return parsedUrl;
        } catch (error) {
            console.error('Invalid Syft URL:', error.message);
            return null;
        }
    }

    /**
     * Update the UI based on the current app state
     */
    function updateUIFromState() {
        // Update form fields
        serverUrlInput.value = appState.serverUrl;
        fromEmailInput.value = appState.fromEmail;
        toEmailInput.value = appState.toEmail;
        appNameInput.value = appState.appName;
        appEndpointInput.value = appState.appEndpoint;
        autoResumeCheckbox.checked = appState.autoResume;

        // Update Syft URL
        syftUrlInput.value = buildSyftUrl();

        // Update headers list
        headersList.innerHTML = '';
        appState.headers.forEach(header => {
            addHeaderToUI(header.key, header.value);
        });

        // Update request body
        requestBodyTextarea.value = appState.requestBody;

        // Configure SDK
        syftFetch.configure({
            serverUrl: appState.serverUrl,
            autoResumeActiveRequests: appState.autoResume
        });
    }

    /**
     * Load app state from local storage
     */
    function loadAppState() {
        try {
            const savedState = localStorage.getItem(STORAGE_KEY);
            if (savedState) {
                appState = JSON.parse(savedState);
                console.log('Loaded state from storage:', appState);
            }
        } catch (error) {
            console.error('Failed to load state from storage:', error);
            appState = { ...defaultState };
        }

        updateUIFromState();
        refreshUI();
    }

    /**
     * Save the current app state to local storage
     */
    function saveAppState() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(appState));
        } catch (error) {
            console.error('Failed to save state to storage:', error);
            showToast('Failed to save settings', 'error');
        }
    }

    /**
     * Reset app state to defaults
     */
    function resetToDefaults() {
        appState = { ...defaultState };
        updateUIFromState();
        saveAppState();
        showToast('Reset to defaults', 'info');
    }

    /**
     * Add a header input row to the UI
     * @param {string} key - The header key
     * @param {string} value - The header value
     */
    function addHeaderToUI(key = '', value = '') {
        const headerItem = document.createElement('div');
        headerItem.className = 'header-item';

        const keyInput = document.createElement('input');
        keyInput.type = 'text';
        keyInput.placeholder = 'Header Key';
        keyInput.value = key;
        keyInput.addEventListener('input', function () {
            const index = Array.from(headerItem.parentNode.children).indexOf(headerItem);
            if (index !== -1) {
                appState.headers[index].key = this.value;
                // If this is x-syft-raw, update the value input to be a checkbox
                if (this.value === 'x-syft-raw') {
                    valueInput.type = 'checkbox';
                    valueInput.checked = value.toLowerCase() === 'true';
                } else {
                    valueInput.type = 'text';
                    valueInput.value = value;
                }
                saveAppState();
            }
        });

        const valueInput = document.createElement('input');
        valueInput.type = key === 'x-syft-raw' ? 'checkbox' : 'text';
        valueInput.placeholder = 'Header Value';
        if (key === 'x-syft-raw') {
            valueInput.checked = value.toLowerCase() === 'true';
        } else {
            valueInput.value = value;
        }
        valueInput.addEventListener('input', function () {
            const index = Array.from(headerItem.parentNode.children).indexOf(headerItem);
            if (index !== -1) {
                if (key === 'x-syft-raw') {
                    appState.headers[index].value = this.checked.toString();
                } else {
                    appState.headers[index].value = this.value;
                }
                saveAppState();
            }
        });

        const removeBtn = document.createElement('div');
        removeBtn.className = 'remove-header';
        removeBtn.innerHTML = '✕';
        removeBtn.addEventListener('click', function () {
            const index = Array.from(headerItem.parentNode.children).indexOf(headerItem);
            if (index !== -1) {
                appState.headers.splice(index, 1);
                headerItem.remove();
                saveAppState();
            }
        });

        headerItem.appendChild(keyInput);
        headerItem.appendChild(valueInput);
        headerItem.appendChild(removeBtn);

        headersList.appendChild(headerItem);
    }

    /**
     * Format the JSON in the request body textarea
     */
    function formatJson() {
        try {
            const json = JSON.parse(requestBodyTextarea.value);
            requestBodyTextarea.value = JSON.stringify(json, null, 2);
            appState.requestBody = requestBodyTextarea.value;
            saveAppState();
        } catch (error) {
            showToast('Invalid JSON', 'error');
        }
    }

    /**
     * Collect headers from the UI state
     * @returns {object} The headers object
     */
    function collectHeaders() {
        const headers = {};

        // Add the from email header
        headers['x-syft-from'] = appState.fromEmail;

        // Add custom headers
        appState.headers.forEach(header => {
            if (header.key && header.value) {
                // Convert boolean strings to actual booleans for x-syft-raw
                if (header.key === 'x-syft-raw') {
                    headers[header.key] = header.value.toLowerCase() === 'true';
                } else {
                    headers[header.key] = header.value;
                }
            }
        });

        return headers;
    }

    /**
     * Get display class for a request status
     * @param {string} status - The request status
     * @returns {string} The CSS class to use
     */
    function getStatusClass(status) {
        switch (status) {
            case 'PENDING':
            case 'POLLING':
                return 'primary';
            case 'SUCCESS':
                return 'success';
            case 'ERROR':
                return 'error';
            default:
                return 'primary';
        }
    }

    /**
     * Format data for display in the request details panel
     * @param {any} data - The data to format
     * @returns {string} HTML-formatted string
     */
    function formatDataForDisplay(data) {
        if (!data) return 'No data';

        try {
            // If already an object, stringify it
            const jsonData = typeof data === 'object' ? data : JSON.parse(data);
            return JSON.stringify(jsonData, null, 2)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;')
                .replace(/\n/g, '<br>')
                .replace(/ /g, '&nbsp;');
        } catch (e) {
            // Not JSON, return as string
            return String(data)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }
    }

    // ==========================================
    // Request Management Functions
    // ==========================================

    /**
     * Refresh the requests list in the UI
     */
    function refreshRequestsList() {
        const allRequests = syftFetch.getAllRequests();

        if (DEBUG) {
            console.log('Refreshing requests list:', allRequests);
        }

        requestsList.innerHTML = '';

        // Sort by timestamp (newest first)
        allRequests.sort((a, b) => b.timestamp - a.timestamp);

        if (allRequests.length === 0) {
            const emptyItem = document.createElement('div');
            emptyItem.className = 'request-item';
            emptyItem.textContent = 'No requests yet';
            requestsList.appendChild(emptyItem);
            return;
        }

        // Create UI elements for each request
        allRequests.forEach(request => {
            const requestItem = document.createElement('div');
            requestItem.className = 'request-item';
            if (activeRequestId === request.id) {
                requestItem.className += ' active';
            }
            requestItem.dataset.id = request.id;
            requestItem.dataset.status = request.status;

            const endpoint = document.createElement('div');
            endpoint.className = 'request-endpoint';

            const method = document.createElement('span');
            method.className = 'request-method';
            method.textContent = request.requestData.method || 'POST';

            endpoint.appendChild(method);
            endpoint.appendChild(document.createTextNode(request.requestData.appEndpoint));

            const status = document.createElement('div');
            status.className = `request-status status-${request.status.toLowerCase()}`;

            // Show polling progress if available
            if (request.status === 'POLLING' && request.pollAttempt > 0) {
                status.textContent = `POLLING (${request.pollAttempt}/${request.maxPollAttempts})`;
            } else {
                status.textContent = request.status;
            }

            const timestamp = document.createElement('div');
            timestamp.className = 'request-timestamp';
            timestamp.textContent = new Date(request.timestamp).toLocaleTimeString();

            // Actions for this request
            const actions = document.createElement('div');
            actions.className = 'request-actions';

            // Only show resume button for PENDING/POLLING requests
            if (request.status === 'PENDING' || request.status === 'POLLING') {
                const resumeBtn = document.createElement('button');
                resumeBtn.className = 'btn-secondary';
                resumeBtn.textContent = 'Resume';
                resumeBtn.addEventListener('click', function (e) {
                    e.stopPropagation(); // Don't trigger the parent click
                    resumeRequest(request.id);
                });
                actions.appendChild(resumeBtn);
            }

            // Delete button
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-danger';
            deleteBtn.textContent = 'Delete';
            deleteBtn.addEventListener('click', function (e) {
                e.stopPropagation(); // Don't trigger the parent click
                deleteRequest(request.id);
            });
            actions.appendChild(deleteBtn);

            requestItem.appendChild(endpoint);
            requestItem.appendChild(status);
            requestItem.appendChild(timestamp);
            requestItem.appendChild(actions);

            requestItem.addEventListener('click', function () {
                selectRequest(request.id);
            });

            requestsList.appendChild(requestItem);
        });

        // If no active request but we have requests, select the first one
        if (!activeRequestId && allRequests.length > 0) {
            selectRequest(allRequests[0].id);
        }
    }

    /**
     * Refresh the request details panel
     * @param {string} requestId - The ID of the request to show details for
     */
    function refreshRequestDetails(requestId) {
        const request = syftFetch.getRequestById(requestId);

        if (!request) {
            requestDetails.innerHTML = '<div class="no-details">Select a request to view details</div>';
            return;
        }

        if (DEBUG) {
            console.log('Refreshing details for request:', request);
        }

        // Build status display with polling info if available
        let statusDisplay = request.status;
        if (request.status === 'POLLING' && request.pollAttempt > 0) {
            const percentComplete = Math.round((request.pollAttempt / request.maxPollAttempts) * 100);
            statusDisplay = `${request.status} (${request.pollAttempt}/${request.maxPollAttempts})`;
            statusDisplay += `<div class="polling-progress-bar"><div class="polling-progress" style="width: ${percentComplete}%"></div></div>`;
        }

        let detailsHTML = `
            <div class="details-section">
                <div class="details-title">Request</div>
                <div class="details-content">
                    <div><strong>ID:</strong> ${request.id}</div>
                    <div><strong>URL:</strong> ${request.requestData.syftUrl}</div>
                    <div><strong>Method:</strong> ${request.requestData.method || 'POST'}</div>
                    <div><strong>Status:</strong> <span class="badge badge-${getStatusClass(request.status)}">${statusDisplay}</span></div>
                    <div><strong>Timestamp:</strong> ${new Date(request.timestamp).toLocaleString()}</div>
                    ${request.requestId ? `<div><strong>Request ID:</strong> ${request.requestId}</div>` : ''}
                </div>
            </div>
            
            <div class="details-section">
                <div class="details-title">Headers</div>
                <div class="details-content">
                    ${Object.entries(request.requestData.headers || {}).map(([key, value]) =>
            `<div><strong>${key}:</strong> ${value}</div>`).join('') || 'No headers'}
                </div>
            </div>
            
            <div class="details-section">
                <div class="details-title">Request Body</div>
                <div class="details-content">
                    <div class="json-viewer">${formatDataForDisplay(request.requestData.body)}</div>
                </div>
            </div>
        `;

        // Add response section if available
        if (request.responseData) {
            detailsHTML += `
                <div class="details-section">
                    <div class="details-title">Response</div>
                    <div class="details-content">
                        <div class="json-viewer">${formatDataForDisplay(request.responseData)}</div>
                    </div>
                </div>
            `;
        }

        // Add error section if available
        if (request.error) {
            detailsHTML += `
                <div class="details-section">
                    <div class="details-title">Error</div>
                    <div class="details-content error-content">
                        ${request.error}
                    </div>
                </div>
            `;
        }

        requestDetails.innerHTML = detailsHTML;
    }

    /**
     * Refresh both the requests list and details panel
     */
    function refreshUI() {
        refreshRequestsList();
        if (activeRequestId) {
            refreshRequestDetails(activeRequestId);
        }
    }

    /**
     * Select a request and show its details
     * @param {string} requestId - The ID of the request to select
     */
    function selectRequest(requestId) {
        activeRequestId = requestId;

        // Update UI selection
        document.querySelectorAll('.request-item').forEach(item => {
            item.classList.remove('active');
        });

        const selectedItem = document.querySelector(`.request-item[data-id="${requestId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('active');
        }

        refreshRequestDetails(requestId);
    }

    /**
     * Resume a request
     * @param {string} requestId - The ID of the request to resume
     */
    function resumeRequest(requestId) {
        showToast('Resuming request...', 'info');

        syftFetch.resumeRequest(requestId)
            .then(() => {
                showToast('Request resumed', 'success');
                refreshUI();
            })
            .catch(error => {
                showToast(`Failed to resume request: ${error.message}`, 'error');
            });
    }

    /**
     * Delete a request
     * @param {string} requestId - The ID of the request to delete
     */
    function deleteRequest(requestId) {
        if (syftFetch.clearRequest(requestId)) {
            // If we're deleting the active request, clear it
            if (activeRequestId === requestId) {
                activeRequestId = null;
            }

            showToast('Request deleted', 'info');
            refreshUI();
        }
    }

    /**
     * Send a new request
     */
    async function sendRequest() {
        const syftUrl = syftUrlInput.value;

        if (!syftUrl) {
            showToast('Syft URL is required', 'error');
            return;
        }

        const headers = collectHeaders();
        const body = requestBodyTextarea.value;

        // Disable the send button while sending
        sendRequestBtn.disabled = true;
        showToast('Sending request...', 'info');

        try {
            if (DEBUG) {
                console.log('Sending request:', {
                    url: syftUrl,
                    headers,
                    body
                });
            }

            const request = await syftFetch(syftUrl, {
                method: 'POST',
                headers,
                body
            });

            // If we got back a SyftRequest object, the request is being processed
            if (request && request.id) {
                if (DEBUG) {
                    console.log('Request created:', request);
                }

                // Select and show this request
                activeRequestId = request.id;
                refreshUI();

                // Add a status change listener
                request.onStatusChange((status) => {
                    if (DEBUG) {
                        console.log(`Request ${request.id} status changed to ${status}`);
                    }

                    // Update UI when status changes
                    refreshUI();

                    if (status === 'SUCCESS') {
                        showToast('Request completed successfully', 'success');
                    } else if (status === 'ERROR') {
                        showToast(`Request failed: ${request.error}`, 'error');
                    } else if (status === 'POLLING_PROGRESS') {
                        // For polling progress updates (no toast, just UI update)
                        refreshUI();
                    }
                });

                showToast('Request sent, waiting for response...', 'info');
            } else {
                // Direct response (already complete)
                if (DEBUG) {
                    console.log('Got immediate response:', request);
                }
                showToast('Request completed successfully', 'success');
                refreshUI();
            }
        } catch (error) {
            console.error('Request failed:', error);
            showToast(`Request failed: ${error.message}`, 'error');
        } finally {
            // Re-enable the send button
            sendRequestBtn.disabled = false;
        }
    }

    /**
     * Test connection to the server
     */
    async function testServerConnection() {
        const serverUrl = serverUrlInput.value;

        if (!serverUrl) {
            showToast('Server URL is required', 'error');
            return;
        }

        showToast('Testing server connection...', 'info');

        try {
            const response = await fetch(serverUrl, {
                method: 'HEAD',
                mode: 'cors'
            });

            if (response.ok) {
                showToast('Server connection successful', 'success');
            } else {
                showToast(`Server connection failed: ${response.status}`, 'error');
            }
        } catch (error) {
            showToast(`Connection failed: ${error.message}`, 'error');
        }
    }

    /**
     * Validate the entered Syft URL
     */
    function validateUrl() {
        const syftUrl = syftUrlInput.value;

        if (!syftUrl) {
            showToast('Syft URL is required', 'error');
            return;
        }

        const parsedUrl = parseSyftUrl(syftUrl);
        if (parsedUrl) {
            showToast('Syft URL is valid', 'success');

            // Update form fields
            appState.toEmail = parsedUrl.toEmail;
            appState.appName = parsedUrl.appName;
            appState.appEndpoint = parsedUrl.appEndpoint;

            updateUIFromState();
            saveAppState();
        } else {
            showToast('Invalid Syft URL', 'error');
        }
    }

    /**
     * Setup request status change listeners for all existing requests
     */
    function setupRequestListeners() {
        if (DEBUG) {
            console.log('Setting up listeners for existing requests');
        }

        const requests = syftFetch.getAllRequests();

        requests.forEach(request => {
            request.onStatusChange((status) => {
                if (DEBUG) {
                    console.log(`Status change for request ${request.id}: ${status}`);
                }
                refreshUI();
            });
        });
    }

    /**
     * Resume all active requests
     */
    function resumeAllRequests() {
        const activeRequests = syftFetch.getActiveRequests();

        if (activeRequests.length > 0) {
            showToast(`Resuming ${activeRequests.length} active requests...`, 'info');

            syftFetch.resumeAllActiveRequests()
                .then(() => {
                    showToast('All active requests resumed', 'success');
                    refreshUI();
                })
                .catch(error => {
                    console.error('Failed to resume all requests:', error);
                    showToast('Failed to resume some requests', 'error');
                });
        }
    }

    /**
     * Setup polling for UI updates
     */
    function startPollingForUpdates() {
        // Check for UI updates every 250ms
        setInterval(() => {
            refreshUI();
        }, 250);
    }

    // ==========================================
    // Event Listeners
    // ==========================================

    // Function to update headers based on input changes
    function updateHeadersFromInput(inputElement, headerKey) {
        const newValue = inputElement.value.trim();
        appState.headers.forEach(header => {
            if (header.key === headerKey) {
                header.value = newValue;
            }
        });

        saveAppState();
        updateUIFromState();
    }

    // Input field change events
    syftUrlInput.addEventListener('input', function () {
        const url = this.value.trim();
        if (url) {
            const parsedUrl = parseSyftUrl(url);
            if (parsedUrl) {
                appState.toEmail = parsedUrl.toEmail;
                appState.appName = parsedUrl.appName;
                appState.appEndpoint = parsedUrl.appEndpoint;

                // Update UI silently
                toEmailInput.value = appState.toEmail;
                appNameInput.value = appState.appName;
                appEndpointInput.value = appState.appEndpoint;

                updateHeadersFromInput(toEmailInput, 'x-syft-to');
                updateHeadersFromInput(appNameInput, 'x-syft-app');
                updateHeadersFromInput(appEndpointInput, 'x-syft-appep');

                saveAppState();
            }
        }
    });

    serverUrlInput.addEventListener('input', function () {
        appState.serverUrl = this.value.trim();
        saveAppState();
    });

    fromEmailInput.addEventListener('input', function () {
        appState.fromEmail = this.value.trim();
        updateHeadersFromInput(this, 'x-syft-from');
        saveAppState();
    });

    toEmailInput.addEventListener('input', function () {
        appState.toEmail = this.value.trim();
        syftUrlInput.value = buildSyftUrl();
        updateHeadersFromInput(this, 'x-syft-to');
        saveAppState();
    });

    appNameInput.addEventListener('input', function () {
        appState.appName = this.value.trim();
        syftUrlInput.value = buildSyftUrl();
        updateHeadersFromInput(this, 'x-syft-app');
        saveAppState();
    });

    appEndpointInput.addEventListener('input', function () {
        appState.appEndpoint = this.value.trim();
        syftUrlInput.value = buildSyftUrl();
        updateHeadersFromInput(this, 'x-syft-appep');
        saveAppState();
    });

    autoResumeCheckbox.addEventListener('change', function () {
        appState.autoResume = this.checked;
        saveAppState();

        // Update SDK config
        syftFetch.configure({
            autoResumeActiveRequests: appState.autoResume
        });
    });

    // Button click events
    testConnectionBtn.addEventListener('click', testServerConnection);
    validateUrlBtn.addEventListener('click', validateUrl);

    resetDefaultsBtn.addEventListener('click', resetToDefaults);

    addHeaderBtn.addEventListener('click', function () {
        appState.headers.push({ key: '', value: '' });
        addHeaderToUI();
        saveAppState();
    });

    formatJsonBtn.addEventListener('click', formatJson);

    sendRequestBtn.addEventListener('click', sendRequest);

    clearRequestsBtn.addEventListener('click', function () {
        syftFetch.clearAllRequests();
        activeRequestId = null;
        requestDetails.innerHTML = '<div class="no-details">Select a request to view details</div>';
        refreshUI();
        showToast('All requests cleared', 'info');
    });

    requestBodyTextarea.addEventListener('input', function () {
        appState.requestBody = this.value;
        saveAppState();
    });

    // ==========================================
    // Initialization
    // ==========================================

    // Load the saved state
    loadAppState();

    // Setup request listeners
    setupRequestListeners();

    // Resume active requests if enabled
    if (appState.autoResume) {
        setTimeout(() => {
            resumeAllRequests();
        }, 100);
    }

    // Start polling for updates
    startPollingForUpdates();

    console.log('SyftBox RPC Tester initialized');
});