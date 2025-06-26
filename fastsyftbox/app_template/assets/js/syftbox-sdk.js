(function (global) {
    // Constants
    const CONSTANTS = {
        STORAGE_KEY: 'syftbox-requests',
        DEFAULT_SERVER_URL: 'https://dev.syftbox.net/',
        DEFAULT_POLLING_INTERVAL: 3000,
        DEFAULT_MAX_POLL_ATTEMPTS: 20,
        DEFAULT_TIMEOUT: 5000,
        MAX_BACKOFF_DELAY: 30000
    };

    // Utility functions
    const utils = {
        generateUUID() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        },

        isValidUrl(url) {
            try {
                new URL(url);
                return true;
            } catch {
                return false;
            }
        },

        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    };

    // Storage management
    const storage = {
        save(requests) {
            try {
                localStorage.setItem(CONSTANTS.STORAGE_KEY, JSON.stringify(requests));
            } catch (error) {
                if (error.name === 'QuotaExceededError') {
                    this.clear();
                    this.save(requests);
                }
                throw new SyftError('Storage error', 'STORAGE_ERROR', { originalError: error });
            }
        },

        load() {
            try {
                const data = localStorage.getItem(CONSTANTS.STORAGE_KEY);
                return data ? JSON.parse(data) : {};
            } catch (error) {
                console.error('Error loading saved requests:', error);
                return {};
            }
        },

        clear() {
            localStorage.removeItem(CONSTANTS.STORAGE_KEY);
        }
    };

    // Error handling
    class SyftError extends Error {
        constructor(message, code, details = {}) {
            super(message);
            this.name = 'SyftError';
            this.code = code;
            this.details = details;
        }
    }

    // Request class
    class SyftRequest {
        constructor(id, requestData) {
            this.id = id;
            this.requestId = null; // Will be set during polling
            this.requestData = requestData;
            this.status = 'PENDING';
            this.timestamp = Date.now();
            this.callbacks = [];
            this.responseData = null;
            this.error = null;
            this.pollTimer = null;
            this.pollAttempt = 0;
            this.maxPollAttempts = CONSTANTS.DEFAULT_MAX_POLL_ATTEMPTS;
        }

        updateStatus(status, data) {
            const oldStatus = this.status;
            this.status = status;

            if (status === 'SUCCESS') {
                this.responseData = data;
                this.pollAttempt = 0;
            } else if (status === 'ERROR') {
                this.error = data;
                this.pollAttempt = 0;
            } else if (status === 'POLLING') {
                if (!this.requestId || data) {
                    this.requestId = data;
                }
            }

            storage.save({ ...storage.load(), [this.id]: this.serialize() });
            console.log(`Request ${this.id} status changed: ${oldStatus} -> ${status}`);

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
            this.timestamp = Date.now();
            storage.save({ ...storage.load(), [this.id]: this.serialize() });
            this.callbacks.forEach(callback => {
                try {
                    callback('POLLING_PROGRESS', this);
                } catch (e) {
                    console.error('Error in polling progress callback:', e);
                }
            });
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
            Object.assign(request, {
                status: data.status,
                timestamp: data.timestamp,
                responseData: data.responseData,
                error: data.error,
                requestId: data.requestId,
                pollAttempt: data.pollAttempt || 0,
                maxPollAttempts: data.maxPollAttempts || CONSTANTS.DEFAULT_MAX_POLL_ATTEMPTS,
                sdk
            });
            return request;
        }

        async resume(sdk) {
            if (this.status === 'SUCCESS' || this.status === 'ERROR') {
                return this;
            }

            this.sdk = sdk;

            if (this.requestId && this.status === 'POLLING') {
                this.updateStatus('POLLING', this.requestId);
                try {
                    const { syftUrl, fromEmail, headers } = this.requestData;
                    const rawParam = headers?.['x-syft-raw'] ? `&x-syft-raw=${headers['x-syft-raw']}` : '';
                    const pollUrlPath = `/api/v1/send/poll?x-syft-from=${fromEmail}&x-syft-url=${encodeURIComponent(syftUrl)}${rawParam}`;

                    const response = await sdk.pollForResponse({
                        pollUrlPath,
                        requestId: this.requestId,
                        request: this
                    });
                    this.updateStatus('SUCCESS', response);
                    return this;
                } catch (error) {
                    this.updateStatus('ERROR', error.message);
                    throw error;
                }
            }
            return await sdk.sendRequest(this);
        }

        async getResult() {
            if (this.status === 'SUCCESS') return this.responseData;
            if (this.status === 'ERROR') throw new SyftError(this.error, 'REQUEST_ERROR');

            return new Promise((resolve, reject) => {
                const checkStatus = (status) => {
                    if (status === 'SUCCESS') resolve(this.responseData);
                    if (status === 'ERROR') reject(new SyftError(this.error, 'REQUEST_ERROR'));
                };
                this.onStatusChange(checkStatus);
                checkStatus(this.status);
            });
        }
    }

    // Polling manager
    class PollingManager {
        constructor(config) {
            this.interval = config.pollingInterval || CONSTANTS.DEFAULT_POLLING_INTERVAL;
            this.maxAttempts = config.maxPollAttempts || CONSTANTS.DEFAULT_MAX_POLL_ATTEMPTS;
        }

        async poll(pollFn, onProgress) {
            let attempt = 0;
            while (attempt < this.maxAttempts) {
                try {
                    const result = await pollFn();
                    if (result) return result;

                    await utils.delay(this.getBackoffDelay(attempt));
                    attempt++;
                    onProgress?.(attempt, this.maxAttempts);
                } catch (error) {
                    if (attempt === this.maxAttempts - 1) throw error;
                }
            }
            throw new SyftError('Polling timeout', 'POLLING_TIMEOUT');
        }

        getBackoffDelay(attempt) {
            return Math.min(1000 * Math.pow(2, attempt), CONSTANTS.MAX_BACKOFF_DELAY);
        }
    }

    // SDK class
    class SyftBoxSDK {
        constructor(config = {}) {
            this.config = this.validateConfig({
                serverUrl: "https://syftbox.net/",
                autoResumeActiveRequests: true,
                pollingInterval: CONSTANTS.DEFAULT_POLLING_INTERVAL,
                maxPollAttempts: CONSTANTS.DEFAULT_MAX_POLL_ATTEMPTS,
                timeout: CONSTANTS.DEFAULT_TIMEOUT,
                ...config
            });

            this.serverUrl = this.config.serverUrl;
            this.autoResumeActiveRequests = this.config.autoResumeActiveRequests;
            this.requests = {};
            this.pollingManager = new PollingManager(this.config);

            this._setupStorageObserver();
            this._refreshRequestsFromStorage();

            if (this.autoResumeActiveRequests) {
                this.resumeAllActiveRequests();
            }
        }

        validateConfig(config) {
            if (config.serverUrl && !utils.isValidUrl(config.serverUrl)) {
                throw new SyftError('Invalid server URL', 'INVALID_CONFIG');
            }
            return config;
        }

        _setupStorageObserver() {
            window.addEventListener('storage', (event) => {
                if (event.key === CONSTANTS.STORAGE_KEY) {
                    this._refreshRequestsFromStorage();
                }
            });
            setInterval(() => this._refreshRequestsFromStorage(), 1000);
        }

        _refreshRequestsFromStorage() {
            try {
                this.requests = storage.load();
            } catch (error) {
                console.error('Error refreshing requests from storage:', error);
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
            this._refreshRequestsFromStorage();
            const fromEmail = options.headers?.['x-syft-from'] || 'anonymous@syft.local';
            const method = options.method || 'POST';
            const body = options.body;

            const requestData = { syftUrl, fromEmail, method, headers: options.headers, body };
            const id = utils.generateUUID();
            const request = new SyftRequest(id, requestData);
            request.sdk = this;

            this.requests[id] = request.serialize();
            storage.save(this.requests);

            return this.sendRequest(request);
        }

        async sendRequest(request) {
            const { syftUrl, fromEmail, method, headers, body } = request.requestData;

            const combinedHeaders = {
                'Content-Type': 'application/json',
                'x-syft-from': fromEmail,
                'timeout': this.config.timeout,
                ...headers,
            };

            try {
                const rawParam = headers?.['x-syft-raw'] ? `&x-syft-raw=${headers['x-syft-raw']}` : '';
                const msgUrl = `${this.serverUrl}api/v1/send/msg?x-syft-from=${fromEmail}&x-syft-url=${encodeURIComponent(syftUrl)}${rawParam}`;

                const response = await fetch(msgUrl, {
                    method,
                    headers: combinedHeaders,
                    body,
                    mode: 'cors'
                });

                if (response.status === 202) {
                    const responseBody = await response.json();
                    if (!responseBody?.request_id) {
                        throw new SyftError('Accepted but missing request_id', 'INVALID_RESPONSE');
                    }

                    request.updateStatus('POLLING', responseBody.request_id);
                    for (const [key, value] of response.headers.entries()) {
                        console.log(`Header: ${key} = ${value}`);
                    }

                    const pollUrl = responseBody.data?.poll_url;
                    const locationHeader = response.headers.get('Location');

                    const pollResult = await this.pollForResponse({
                        requestId: responseBody.request_id,
                        pollUrlPath: pollUrl || locationHeader,
                        request
                    });

                    request.updateStatus('SUCCESS', pollResult);
                    return pollResult;
                }

                if (response.ok) {
                    const responseData = await response.json();
                    request.updateStatus('SUCCESS', responseData);
                    return responseData;
                }

                const errorText = await response.text();
                throw new SyftError(`Error ${response.status}: ${errorText}`, 'REQUEST_ERROR');
            } catch (error) {
                request.updateStatus('ERROR', error.message);
                throw error;
            }
        }

        async pollForResponse({ requestId, pollUrlPath, request }) {
            const pollUrl = `${this.serverUrl}${pollUrlPath.replace(/^\//, '')}`;

            return this.pollingManager.poll(
                async () => {
                    const response = await fetch(pollUrl, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        }
                    });

                    const body = await response.json().catch(() => ({}));

                    if (!response.ok) {
                        if (response.status === 500 && body.error === "No response exists. Polling timed out") {
                            return null;
                        }
                        // if the request is not found, we can't poll for it
                        else if (response.status === 404) {
                            return {
                                status: 'ERROR',
                                message: body.message || 'No request found.',
                                request_id: requestId
                            };
                        }
                        throw new SyftError(`Polling failed: ${response.status}`, 'POLLING_ERROR');
                    }

                    // Handle 202 status with timeout error - continue polling
                    if (response.status === 202 && body.error === 'timeout') {
                        console.log(`Polling timeout for request ${requestId}, continuing to poll...`);
                        return null;
                    }

                    // Handle successful responses
                    if (body.status === 'pending') {
                        return null;
                    }

                    // Check if we have actual response data
                    if (body.response || (!body.error && body.request_id)) {
                        return body.response || body;
                    }

                    // If we get here with an error, it's a real error
                    if (body.error) {
                        throw new SyftError(`Polling error: ${body.message || body.error}`, 'POLLING_ERROR');
                    }

                    return body.response || body;
                },
                (attempt, maxAttempts) => request?.updatePollingProgress(attempt, maxAttempts)
            );
        }

        getRequestById(id) {
            this._refreshRequestsFromStorage();
            const requestData = this.requests[id];
            return requestData ? SyftRequest.deserialize(requestData, this) : null;
        }

        getAllRequests() {
            this._refreshRequestsFromStorage();
            return Object.values(this.requests).map(req => SyftRequest.deserialize(req, this));
        }

        getActiveRequests() {
            return this.getAllRequests().filter(
                req => req.status === 'PENDING' || req.status === 'POLLING'
            );
        }

        async resumeRequest(requestId) {
            this._refreshRequestsFromStorage();
            const request = this.getRequestById(requestId);
            if (!request) {
                throw new SyftError(`Request with ID ${requestId} not found`, 'REQUEST_NOT_FOUND');
            }
            return await request.resume(this);
        }

        async resumeAllActiveRequests() {
            const activeRequests = this.getActiveRequests();
            console.log(`Resuming ${activeRequests.length} active requests...`);

            await Promise.all(
                activeRequests.map(request =>
                    request.resume(this).catch(error => {
                        console.error(`Failed to resume request ${request.id}:`, error);
                        return null;
                    })
                )
            );
            console.log('All active requests resumed');
        }

        clearRequest(requestId) {
            this._refreshRequestsFromStorage();
            if (this.requests[requestId]) {
                delete this.requests[requestId];
                storage.save(this.requests);
                return true;
            }
            return false;
        }

        clearAllRequests() {
            this.requests = {};
            storage.save(this.requests);
        }

        configure(options) {
            this.config = this.validateConfig({ ...this.config, ...options });
            if (options.serverUrl) this.serverUrl = options.serverUrl;
            if (options.autoResumeActiveRequests !== undefined) {
                this.autoResumeActiveRequests = options.autoResumeActiveRequests;
            }
            if (options.autoResumeActiveRequests && !this.autoResumeActiveRequests) {
                this.resumeAllActiveRequests();
            }
        }
    }

    // Create singleton instance
    const sdk = new SyftBoxSDK();

    // Public API
    const syftFetch = async (syftUrl, options) => {
        return await sdk.syftFetch(syftUrl, options);
    };

    // Expose methods
    syftFetch.configure = options => sdk.configure(options);
    syftFetch.getRequestById = requestId => sdk.getRequestById(requestId);
    syftFetch.getAllRequests = () => sdk.getAllRequests();
    syftFetch.getActiveRequests = () => sdk.getActiveRequests();
    syftFetch.resumeRequest = requestId => sdk.resumeRequest(requestId);
    syftFetch.resumeAllActiveRequests = () => sdk.resumeAllActiveRequests();
    syftFetch.clearRequest = requestId => sdk.clearRequest(requestId);
    syftFetch.clearAllRequests = () => sdk.clearAllRequests();

    // Server URL property
    Object.defineProperty(syftFetch, 'serverUrl', {
        get() { return sdk.serverUrl; },
        set(value) { sdk.configure({ serverUrl: value }); }
    });

    // Global export
    global.syftFetch = syftFetch;
    global.SyftBoxSDK = SyftBoxSDK;

})(window);