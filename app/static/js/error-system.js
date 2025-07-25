/**
 * Advanced Error Management System for IPTV PVR
 * Provides user-friendly error display with copyable debug information
 */

class ErrorSystem {
    constructor() {
        this.errorContainer = null;
        this.recentErrors = [];
        this.maxErrors = 50;
        this.init();
    }
    
    init() {
        // Create floating error container
        this.createErrorContainer();
        
        // Set up global error handlers
        this.setupGlobalHandlers();
        
        // Initialize keyboard shortcuts
        this.setupKeyboardShortcuts();
    }
    
    createErrorContainer() {
        // Create main error display container
        const container = document.createElement('div');
        container.id = 'error-system-container';
        container.className = 'error-system-container';
        container.innerHTML = `
            <div class="error-system-header">
                <span class="error-system-title">
                    <i class="bi bi-exclamation-triangle-fill"></i> Error Console
                </span>
                <button class="error-system-close" onclick="errorSystem.hide()">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>
            <div class="error-system-content" id="error-system-content">
                <!-- Errors will be displayed here -->
            </div>
            <div class="error-system-footer">
                <button class="btn btn-sm btn-outline-secondary" onclick="errorSystem.clearAll()">
                    Clear All
                </button>
                <button class="btn btn-sm btn-outline-primary" onclick="errorSystem.downloadLog()">
                    <i class="bi bi-download"></i> Download Log
                </button>
            </div>
        `;
        
        document.body.appendChild(container);
        this.errorContainer = container;
        
        // Add styles
        this.injectStyles();
    }
    
    injectStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .error-system-container {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 500px;
                max-width: 90vw;
                max-height: 70vh;
                background: var(--bs-body-bg, #fff);
                border: 1px solid var(--bs-border-color, #dee2e6);
                border-radius: 0.5rem;
                box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
                z-index: 9999;
                display: none;
                flex-direction: column;
            }
            
            .error-system-container.show {
                display: flex;
            }
            
            .error-system-header {
                padding: 1rem;
                border-bottom: 1px solid var(--bs-border-color, #dee2e6);
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: var(--bs-gray-100, #f8f9fa);
                border-radius: 0.5rem 0.5rem 0 0;
            }
            
            .error-system-title {
                font-weight: 600;
                color: var(--bs-danger, #dc3545);
            }
            
            .error-system-close {
                background: none;
                border: none;
                font-size: 1.25rem;
                cursor: pointer;
                color: var(--bs-secondary, #6c757d);
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 0.25rem;
                transition: all 0.2s;
            }
            
            .error-system-close:hover {
                background: var(--bs-gray-200, #e9ecef);
                color: var(--bs-dark, #212529);
            }
            
            .error-system-content {
                flex: 1;
                overflow-y: auto;
                padding: 0.5rem;
                max-height: 400px;
            }
            
            .error-system-footer {
                padding: 0.75rem;
                border-top: 1px solid var(--bs-border-color, #dee2e6);
                display: flex;
                justify-content: space-between;
                background: var(--bs-gray-100, #f8f9fa);
                border-radius: 0 0 0.5rem 0.5rem;
            }
            
            .error-item {
                margin-bottom: 0.5rem;
                padding: 0.75rem;
                border: 1px solid var(--bs-border-color, #dee2e6);
                border-radius: 0.375rem;
                background: var(--bs-body-bg, #fff);
            }
            
            .error-item.error-severity-critical {
                border-color: var(--bs-danger, #dc3545);
                background: rgba(220, 53, 69, 0.05);
            }
            
            .error-item.error-severity-error {
                border-color: var(--bs-danger, #dc3545);
            }
            
            .error-item.error-severity-warning {
                border-color: var(--bs-warning, #ffc107);
                background: rgba(255, 193, 7, 0.05);
            }
            
            .error-item.error-severity-info {
                border-color: var(--bs-info, #0dcaf0);
                background: rgba(13, 202, 240, 0.05);
            }
            
            .error-item-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: 0.5rem;
            }
            
            .error-item-title {
                font-weight: 600;
                color: var(--bs-dark, #212529);
                flex: 1;
                margin-right: 0.5rem;
            }
            
            .error-item-time {
                font-size: 0.75rem;
                color: var(--bs-secondary, #6c757d);
                white-space: nowrap;
            }
            
            .error-item-message {
                color: var(--bs-body-color, #212529);
                margin-bottom: 0.5rem;
            }
            
            .error-item-suggestions {
                background: var(--bs-gray-100, #f8f9fa);
                padding: 0.5rem;
                border-radius: 0.25rem;
                margin-bottom: 0.5rem;
            }
            
            .error-item-suggestions-title {
                font-weight: 600;
                font-size: 0.875rem;
                margin-bottom: 0.25rem;
                color: var(--bs-success, #198754);
            }
            
            .error-item-suggestions ul {
                margin: 0;
                padding-left: 1.25rem;
                font-size: 0.875rem;
            }
            
            .error-item-actions {
                display: flex;
                gap: 0.5rem;
                flex-wrap: wrap;
            }
            
            .error-item-actions button {
                font-size: 0.75rem;
                padding: 0.25rem 0.5rem;
            }
            
            .error-details-modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 10000;
                align-items: center;
                justify-content: center;
            }
            
            .error-details-modal.show {
                display: flex;
            }
            
            .error-details-content {
                background: var(--bs-body-bg, #fff);
                border-radius: 0.5rem;
                padding: 1.5rem;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
            }
            
            .error-details-content pre {
                background: var(--bs-gray-100, #f8f9fa);
                padding: 1rem;
                border-radius: 0.25rem;
                overflow-x: auto;
                font-size: 0.875rem;
                white-space: pre-wrap;
                word-break: break-all;
            }
            
            .error-toast {
                position: fixed;
                top: 20px;
                right: 20px;
                max-width: 350px;
                z-index: 10001;
                animation: slideIn 0.3s ease-out;
            }
            
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            
            @media (max-width: 768px) {
                .error-system-container {
                    width: calc(100vw - 40px);
                    right: 20px;
                    left: 20px;
                    bottom: 20px;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    setupGlobalHandlers() {
        // Override console.error to capture errors
        const originalError = console.error;
        console.error = (...args) => {
            originalError.apply(console, args);
            this.captureConsoleError(args);
        };
        
        // Global error handler
        window.addEventListener('error', (event) => {
            this.handleError({
                message: event.message,
                source: event.filename,
                line: event.lineno,
                column: event.colno,
                error: event.error
            });
        });
        
        // Unhandled promise rejection handler
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError({
                message: `Unhandled Promise Rejection: ${event.reason}`,
                error: event.reason
            });
        });
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Shift + E to toggle error console
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'E') {
                e.preventDefault();
                this.toggle();
            }
        });
    }
    
    handleError(errorData) {
        const error = {
            id: this.generateId(),
            timestamp: new Date(),
            ...errorData
        };
        
        this.recentErrors.unshift(error);
        if (this.recentErrors.length > this.maxErrors) {
            this.recentErrors = this.recentErrors.slice(0, this.maxErrors);
        }
        
        this.displayError(error);
        this.showToast(error);
    }
    
    displayError(error) {
        const content = document.getElementById('error-system-content');
        if (!content) return;
        
        const errorElement = document.createElement('div');
        errorElement.className = `error-item error-severity-${error.severity || 'error'}`;
        errorElement.innerHTML = `
            <div class="error-item-header">
                <div class="error-item-title">${this.escapeHtml(error.user_message || error.message || 'Unknown Error')}</div>
                <div class="error-item-time">${this.formatTime(error.timestamp)}</div>
            </div>
            ${error.suggestions ? `
                <div class="error-item-suggestions">
                    <div class="error-item-suggestions-title">Suggestions:</div>
                    <ul>
                        ${error.suggestions.map(s => `<li>${this.escapeHtml(s)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
            <div class="error-item-actions">
                <button class="btn btn-sm btn-outline-primary" onclick="errorSystem.copyError('${error.id}')">
                    <i class="bi bi-clipboard"></i> Copy
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="errorSystem.showDetails('${error.id}')">
                    <i class="bi bi-info-circle"></i> Details
                </button>
                ${error.retry ? `
                    <button class="btn btn-sm btn-outline-success" onclick="${error.retry}">
                        <i class="bi bi-arrow-clockwise"></i> Retry
                    </button>
                ` : ''}
            </div>
        `;
        
        content.insertBefore(errorElement, content.firstChild);
        
        // Auto-show console for critical errors
        if (error.severity === 'critical' || error.severity === 'error') {
            this.show();
        }
    }
    
    showToast(error) {
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.innerHTML = `
            <div class="alert alert-${this.getBootstrapClass(error.severity)} alert-dismissible fade show" role="alert">
                <strong>${this.getIcon(error.severity)} ${this.escapeHtml(error.category || 'Error')}:</strong>
                ${this.escapeHtml(error.user_message || error.message || 'An error occurred')}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
    
    copyError(errorId) {
        const error = this.recentErrors.find(e => e.id === errorId);
        if (!error) return;
        
        const copyText = this.generateCopyableText(error);
        
        // Check if clipboard API is available and we're in a secure context
        if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
            navigator.clipboard.writeText(copyText).then(() => {
                this.showNotification('Error details copied to clipboard', 'success');
            }).catch((err) => {
                console.warn('Clipboard API failed, using fallback:', err);
                this.fallbackCopy(copyText);
            });
        } else {
            // Use fallback for non-HTTPS or when clipboard API is not available
            this.fallbackCopy(copyText);
        }
    }
    
    fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.top = '-9999px';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        
        try {
            textarea.select();
            textarea.setSelectionRange(0, 99999); // For mobile devices
            document.execCommand('copy');
            this.showNotification('Error details copied to clipboard', 'success');
        } catch (err) {
            console.error('Failed to copy:', err);
            this.showNotification('Failed to copy to clipboard', 'error');
        } finally {
            document.body.removeChild(textarea);
        }
    }
    
    generateCopyableText(error) {
        const lines = [
            `Error ID: ${error.error_id || error.id}`,
            `Timestamp: ${error.timestamp.toISOString()}`,
            `Category: ${error.category || 'Unknown'}`,
            `Severity: ${error.severity || 'error'}`,
            `Message: ${error.message}`,
            `User Message: ${error.user_message || 'N/A'}`,
            `Error Code: ${error.error_code || 'N/A'}`,
            ''
        ];
        
        if (error.source) {
            lines.push(`Source: ${error.source}`);
            if (error.line) lines.push(`Line: ${error.line}, Column: ${error.column || 'N/A'}`);
        }
        
        if (error.endpoint) {
            lines.push(`Endpoint: ${error.endpoint}`);
            lines.push(`Method: ${error.method || 'N/A'}`);
        }
        
        if (error.stack) {
            lines.push('', 'Stack Trace:', error.stack);
        }
        
        if (error.technical_details) {
            lines.push('', 'Technical Details:', error.technical_details);
        }
        
        if (error.additional_data) {
            lines.push('', 'Additional Data:', JSON.stringify(error.additional_data, null, 2));
        }
        
        return lines.join('\n');
    }
    
    showDetails(errorId) {
        const error = this.recentErrors.find(e => e.id === errorId);
        if (!error) return;
        
        const modal = document.createElement('div');
        modal.className = 'error-details-modal show';
        modal.innerHTML = `
            <div class="error-details-content">
                <h5>Error Details</h5>
                <pre>${this.escapeHtml(this.generateCopyableText(error))}</pre>
                <div class="mt-3">
                    <button class="btn btn-primary" onclick="errorSystem.copyError('${error.id}')">
                        <i class="bi bi-clipboard"></i> Copy to Clipboard
                    </button>
                    <button class="btn btn-secondary ms-2" onclick="this.closest('.error-details-modal').remove()">
                        Close
                    </button>
                </div>
            </div>
        `;
        
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
        
        document.body.appendChild(modal);
    }
    
    show() {
        this.errorContainer.classList.add('show');
    }
    
    hide() {
        this.errorContainer.classList.remove('show');
    }
    
    toggle() {
        this.errorContainer.classList.toggle('show');
    }
    
    clearAll() {
        const content = document.getElementById('error-system-content');
        if (content) {
            content.innerHTML = '';
        }
        this.recentErrors = [];
        this.showNotification('All errors cleared', 'success');
    }
    
    downloadLog() {
        const log = this.recentErrors.map(error => this.generateCopyableText(error)).join('\n\n' + '='.repeat(80) + '\n\n');
        const blob = new Blob([log], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `iptv-pvr-error-log-${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showNotification('Error log downloaded', 'success');
    }
    
    captureConsoleError(args) {
        const error = {
            message: args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' '),
            source: 'console',
            severity: 'error'
        };
        this.handleError(error);
    }
    
    showNotification(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
    
    // Utility methods
    generateId() {
        return 'error-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    formatTime(date) {
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) return 'just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        
        return date.toLocaleTimeString();
    }
    
    getBootstrapClass(severity) {
        const map = {
            'critical': 'danger',
            'error': 'danger',
            'warning': 'warning',
            'info': 'info'
        };
        return map[severity] || 'secondary';
    }
    
    getIcon(severity) {
        const map = {
            'critical': '🚨',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️'
        };
        return map[severity] || '❓';
    }
}

// Initialize global error system
window.errorSystem = new ErrorSystem();

// Enhanced error handling for API calls
window.handleApiError = function(error, options = {}) {
    const errorData = {
        category: options.category || 'API',
        severity: options.severity || 'error',
        retry: options.retry,
        ...error
    };
    
    if (error.response && error.response.data && error.response.data.error) {
        Object.assign(errorData, error.response.data.error);
    }
    
    window.errorSystem.handleError(errorData);
};

// Helper for import errors
window.handleImportError = function(error, sourceUrl) {
    window.handleApiError(error, {
        category: 'Import',
        additional_data: { source_url: sourceUrl }
    });
};