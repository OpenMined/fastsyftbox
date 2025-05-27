(function (global) {
    // Helper functions
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    // Request storage & persistence
    const REQUEST_STORAGE_KEY = 'syftbox-requests';

    function saveRequests(requests) {
        localStorage.setItem(REQUEST_STORAGE_KEY, JSON.stringify(requests));
    }

    function loadRequests() {
        try {
            const data = localStorage.getItem(REQUEST_STORAGE_KEY);
            return data ? JSON.parse(data) : {};
        } catch (e) {
            console.error('Error loading saved requests:', e);
            return {};
        }
    }

    class SyftRequest {
        constructor(id, requestData) {
            this.id = id;
            this.requestData = requestData;
            this.status = 'PENDING';
            this.timestamp = Date.now();
            this.callbacks = [];
            this.responseData = null;
            this.error = null;
            this.pollTimer = null;
            this.pollAttempt = 0; // Track polling attempts
            this.maxPollAttempts = 20; // Default max attempts
        }

        updateStatus(status, data) {
            const oldStatus = this.status;
            this.status = status;

            if (status === 'SUCCESS') {
                this.responseData = data;
                this.pollAttempt = 0; // Reset poll attempt counter
            } else if (status === 'ERROR') {
                this.error = data;
                this.pollAttempt = 0; // Reset poll attempt counter
            } else if (status === 'POLLING') {
                // Only update requestId on first polling or if it's provided
                if (!this.requestId || data) {
                    this.requestId = data;
                }
            }

            // Save changes to storage
            const requests = loadRequests();
            requests[this.id] = this.serialize();
            saveRequests(requests);

            // Log status changes for debugging
            console.log(`Request ${this.id} status changed: ${oldStatus} -> ${status}`);

            // Notify callbacks
            this.callbacks.forEach(callback => {
                try {
                    callback(status, this);
                } catch (e) {
                    console.error('Error in status callback:', e);
                }
            });
        }

        updatePollingProgress(attempt, maxAttempts) {
            this.pollAttempt = attempt;
            this.maxPollAttempts = maxAttempts;

            // Force a status update to trigger UI refresh
            // Use the same status but with a new timestamp to force changes
            this.timestamp = Date.now();

            // Save changes to storage
            const requests = loadRequests();
            requests[this.id] = this.serialize();
            saveRequests(requests);

            // Notify callbacks with special polling progress status
            this.callbacks.forEach(callback => {
                try {
                    callback('POLLING_PROGRESS', this);
                } catch (e) {
                    console.error('Error in polling progress callback:', e);
                }
            });

            console.log(`Request ${this.id} polling progress: ${attempt}/${maxAttempts}`);
        }

        onStatusChange(callback) {
            this.callbacks.push(callback);
            return this;
        }

        serialize() {
            return {
                id: this.id,
                requestData: this.requestData,
                status: this.status,
                timestamp: this.timestamp,
                responseData: this.responseData,
                error: this.error,
                requestId: this.requestId,
                pollAttempt: this.pollAttempt,
                maxPollAttempts: this.maxPollAttempts
            };
        }

        static deserialize(data, sdk) {
            const request = new SyftRequest(data.id, data.requestData);
            request.status = data.status;
            request.timestamp = data.timestamp;
            request.responseData = data.responseData;
            request.error = data.error;
            request.requestId = data.requestId;
            request.pollAttempt = data.pollAttempt || 0;
            request.maxPollAttempts = data.maxPollAttempts || 20;
            request.sdk = sdk;
            return request;
        }

        // Resume this request if it's in a PENDING or POLLING state
        async resume(sdk) {
            if (this.status === 'SUCCESS' || this.status === 'ERROR') {
                return this;
            }

            this.sdk = sdk;

            // If we have a requestId, we can resume polling
            if (this.requestId && this.status === 'POLLING') {
                this.updateStatus('POLLING', this.requestId);

                try {
                    const { toEmail, appName, appEndpoint } = this.requestData;

                    // Resume polling
                    const response = await sdk.pollForResponse({
                        toEmail,
                        appName,
                        appEndpoint,
                        requestId: this.requestId,
                        request: this // Pass the request object for progress updates
                    });

                    this.updateStatus('SUCCESS', response);
                    return this;
                } catch (error) {
                    this.updateStatus('ERROR', error.message);
                    throw error;
                }
            } else {
                // Otherwise, we need to resend the request
                return await sdk.sendRequest(this);
            }
        }

        // Get the result (waits for completion if needed)
        async getResult() {
            if (this.status === 'SUCCESS') {
                return this.responseData;
            } else if (this.status === 'ERROR') {
                throw new Error(this.error);
            }

            // Return a promise that resolves when the request completes
            return new Promise((resolve, reject) => {
                const checkStatus = (status) => {
                    if (status === 'SUCCESS') {
                        resolve(this.responseData);
                    } else if (status === 'ERROR') {
                        reject(new Error(this.error));
                    }
                };

                this.onStatusChange(checkStatus);
                checkStatus(this.status); // Check current status
            });
        }
    }

    class SyftBoxSDK {
        constructor({ serverUrl = "https://syftboxdev.openmined.org/", autoResumeActiveRequests = true } = {}) {
            this.serverUrl = serverUrl;
            this.autoResumeActiveRequests = autoResumeActiveRequests;

            // Initialize request store
            this.requests = {};

            // FIX: Add storage observer to detect changes from other tabs/instances
            this._setupStorageObserver();

            // Always load fresh data from localStorage
            this._refreshRequestsFromStorage();

            // Auto-resume active requests if enabled
            if (this.autoResumeActiveRequests) {
                this.resumeAllActiveRequests();
            }
        }

        // FIX: Add method to set up storage observer
        _setupStorageObserver() {
            // Listen for storage events (changes from other tabs)
            window.addEventListener('storage', (event) => {
                if (event.key === REQUEST_STORAGE_KEY) {
                    console.log('Storage updated from another tab, refreshing requests');
                    this._refreshRequestsFromStorage();
                }
            });

            // Set up a periodic refresh to make sure we're in sync
            setInterval(() => this._refreshRequestsFromStorage(), 1000);
        }

        // FIX: Add method to refresh requests from storage
        _refreshRequestsFromStorage() {
            try {
                const storedRequests = loadRequests();
                this.requests = storedRequests;
            } catch (error) {
                console.error('Error refreshing requests from storage:', error);
            }
        }

        configure(options) {
            if (options.serverUrl) this.serverUrl = options.serverUrl;
            if (options.autoResumeActiveRequests !== undefined) this.autoResumeActiveRequests = options.autoResumeActiveRequests;

            // If auto-resume was enabled, trigger it
            if (options.autoResumeActiveRequests && !this.autoResumeActiveRequests) {
                this.resumeAllActiveRequests();
            }
        }

        parseSyftUrl(syftUrl) {
            const url = new URL(syftUrl);
            if (url.protocol !== 'syft:') throw new Error('Invalid scheme');
            const toEmail = `${url.username}@${url.hostname}`;
            const pathParts = url.pathname.split('/').filter(Boolean);
            if (pathParts.length < 4 || pathParts[0] !== 'app_data' || pathParts[2] !== 'rpc') {
                throw new Error('Invalid syft URL format');
            }
            const appName = pathParts[1];
            const appEndpoint = pathParts.slice(3).join('/');
            return { toEmail, appName, appEndpoint };
        }

        async syftFetch(syftUrl, options = {}) {
            // FIX: Refresh requests from storage before processing
            this._refreshRequestsFromStorage();

            const { toEmail, appName, appEndpoint } = this.parseSyftUrl(syftUrl);
            const fromEmail = options.headers?.['x-syft-from'] || 'anonymous@syft.local';
            const method = options.method || 'POST';
            const body = options.body;

            // Request metadata
            const requestData = {
                syftUrl,
                toEmail,
                appName,
                appEndpoint,
                fromEmail,
                method,
                headers: options.headers,
                body
            };

            // Create a new request
            const id = generateUUID();
            const request = new SyftRequest(id, requestData);
            request.sdk = this;

            // Store the request 
            this.requests[id] = request.serialize();
            saveRequests(this.requests);
            console.log("Saving request", request.serialize())

            // Send the request
            return this.sendRequest(request);
        }

        async sendRequest(request) {
            const { syftUrl, method, headers, body } = request.requestData;

            // Prepare headers
            const combinedHeaders = {
                'Content-Type': 'application/json',
                'x-syft-msg-type': 'request',
                'x-syft-from': request.requestData.fromEmail,
                'x-syft-to': request.requestData.toEmail,
                'x-syft-app': request.requestData.appName,
                'x-syft-appep': request.requestData.appEndpoint,
                'x-syft-method': method,
                'x-syft-timeout': 5000,
                ...headers,
            };

            try {
                // Construct the message URL
                const msgUrl = `${this.serverUrl}api/v1/send/msg?user=${request.requestData.toEmail}`;

                // Send the request
                const response = await fetch(msgUrl, {
                    method,
                    headers: combinedHeaders,
                    body,
                    mode: 'cors'
                });

                // Handle 202 Accepted (async processing)
                if (response.status === 202) {
                    const responseBody = await response.json();

                    if (responseBody?.request_id) {
                        // Update request status and start polling
                        request.updateStatus('POLLING', responseBody.request_id);

                        // Start polling for the result
                        try {
                            const pollResult = await this.pollForResponse({
                                toEmail: request.requestData.toEmail,
                                appName: request.requestData.appName,
                                appEndpoint: request.requestData.appEndpoint,
                                requestId: responseBody.request_id,
                                request: request // Pass the request object for progress updates
                            });

                            // Update with success
                            request.updateStatus('SUCCESS', pollResult);
                            return pollResult;
                        } catch (pollError) {
                            // Update with error from polling
                            request.updateStatus('ERROR', pollError.message);
                            throw pollError;
                        }
                    } else {
                        const error = 'Accepted but missing request_id';
                        request.updateStatus('ERROR', error);
                        throw new Error(error);
                    }
                }

                // Handle immediate success
                if (response.ok) {
                    const responseData = await response.json();
                    request.updateStatus('SUCCESS', responseData);
                    return responseData;
                }

                // Handle errors
                const errorText = await response.text();
                const error = `Error ${response.status}: ${errorText}`;
                request.updateStatus('ERROR', error);
                throw new Error(error);
            } catch (error) {
                request.updateStatus('ERROR', error.message);
                throw error;
            }
        }

        async pollForResponse({ toEmail, appName, appEndpoint, requestId, request, maxAttempts = 20, interval = 3000 }) {
            const pollUrl = `${this.serverUrl}api/v1/send/poll?user=${toEmail}&app_name=${encodeURIComponent(appName)}&app_endpoint=${encodeURIComponent(appEndpoint)}&request_id=${encodeURIComponent(requestId)}`;

            // Store the max attempts in the request object for tracking
            if (request) {
                request.maxPollAttempts = maxAttempts;
            }

            for (let attempt = 0; attempt < maxAttempts; attempt++) {
                // Update the polling progress in the request object if available
                if (request) {
                    request.updatePollingProgress(attempt + 1, maxAttempts);
                }

                await new Promise(r => setTimeout(r, interval));

                try {
                    const response = await fetch(pollUrl);

                    if (response.ok) {
                        const data = await response.json();

                        // If status is pending, continue polling but update UI
                        if (data.status === 'pending') {
                            // Update request with polling status (to trigger UI refresh)
                            if (request) {
                                // We're still in POLLING state, but update timestamp to trigger UI refresh
                                request.updateStatus('POLLING');
                            }
                            continue;
                        }

                        // Found a result
                        if (data.response) return data.response;
                        return data;
                    } else {
                        const body = await response.json().catch(() => ({}));

                        // Special case for "polling timed out"
                        if (response.status === 500 && body.error === "No response exists. Polling timed out") {
                            // Update request with polling status (to trigger UI refresh)
                            if (request) {
                                request.updateStatus('POLLING');
                            }
                            continue;
                        }

                        throw new Error(`Polling failed: ${response.status}`);
                    }
                } catch (err) {
                    // Only throw on last attempt
                    if (attempt === maxAttempts - 1) {
                        throw new Error(`Polling error: ${err.message}`);
                    }

                    // Update request with polling status but include error info
                    if (request) {
                        request.error = `Polling attempt ${attempt + 1} failed: ${err.message}`;
                        request.updateStatus('POLLING');
                    }
                }
            }

            throw new Error("Polling timed out");
        }

        // Request management methods
        getRequestById(id) {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            const requestData = this.requests[id];
            if (!requestData) return null;

            return SyftRequest.deserialize(requestData, this);
        }

        getAllRequests() {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            return Object.values(this.requests).map(req => SyftRequest.deserialize(req, this));
        }

        getActiveRequests() {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            return this.getAllRequests().filter(
                req => req.status === 'PENDING' || req.status === 'POLLING'
            );
        }

        async resumeRequest(requestId) {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            const request = this.getRequestById(requestId);
            if (!request) {
                throw new Error(`Request with ID ${requestId} not found`);
            }

            return await request.resume(this);
        }

        async resumeAllActiveRequests() {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            const activeRequests = this.getActiveRequests();
            console.log(`Resuming ${activeRequests.length} active requests...`);

            const resumePromises = activeRequests.map(request => {
                return request.resume(this).catch(error => {
                    console.error(`Failed to resume request ${request.id}:`, error);
                    return null;
                });
            });

            await Promise.all(resumePromises);
            console.log('All active requests resumed');
        }

        clearRequest(requestId) {
            // FIX: Always load the latest data first
            this._refreshRequestsFromStorage();

            if (this.requests[requestId]) {
                delete this.requests[requestId];
                saveRequests(this.requests);
                return true;
            }
            return false;
        }

        clearAllRequests() {
            this.requests = {};
            saveRequests(this.requests);
        }
    }

    // Create singleton instance with default config
    const sdk = new SyftBoxSDK();

    // Expose default fetch function
    async function syftFetch(syftUrl, options) {
        return await sdk.syftFetch(syftUrl, options);
    }

    // Expose config capability
    syftFetch.configure = function (options) {
        sdk.configure(options);
    };

    // Expose request management methods
    syftFetch.getRequestById = requestId => sdk.getRequestById(requestId);
    syftFetch.getAllRequests = () => sdk.getAllRequests();
    syftFetch.getActiveRequests = () => sdk.getActiveRequests();
    syftFetch.resumeRequest = requestId => sdk.resumeRequest(requestId);
    syftFetch.resumeAllActiveRequests = () => sdk.resumeAllActiveRequests();
    syftFetch.clearRequest = requestId => sdk.clearRequest(requestId);
    syftFetch.clearAllRequests = () => sdk.clearAllRequests();

    // Optional: get current server
    Object.defineProperty(syftFetch, 'serverUrl', {
        get() {
            return sdk.serverUrl;
        },
        set(value) {
            sdk.configure({ serverUrl: value });
        }
    });

    // Global export
    global.syftFetch = syftFetch;
    global.SyftBoxSDK = SyftBoxSDK;

})(window);