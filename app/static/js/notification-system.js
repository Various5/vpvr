// Global Notification System
// This provides a unified notification system that all other scripts can use

(function() {
    'use strict';
    
    // Create global notification function immediately
    window.showNotification = function(message, type = 'info', details = null, duration = 5000) {
        const toastId = 'toast-' + Date.now();
        const icons = {
            'success': 'bi-check-circle-fill',
            'error': 'bi-x-circle-fill',
            'warning': 'bi-exclamation-triangle-fill',
            'info': 'bi-info-circle-fill'
        };
        
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="bi ${icons[type] || icons.info} me-2"></i>
                        ${escapeHtml(message)}
                        ${details ? `<div class="small mt-1 opacity-75">${escapeHtml(details)}</div>` : ''}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;
        
        // Ensure toast container exists
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }
        
        // Add toast to container
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        // Initialize and show toast
        const toastElement = document.getElementById(toastId);
        if (toastElement && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            const toast = new bootstrap.Toast(toastElement, {
                autohide: true,
                delay: duration
            });
            toast.show();
            
            // Remove from DOM after hidden
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
        } else {
            // Fallback for when Bootstrap isn't ready
            setTimeout(() => {
                const el = document.getElementById(toastId);
                if (el) el.remove();
            }, duration);
        }
    };
    
    // Helper function to escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
    
    // Also expose a simpler alert-based notification for critical errors
    window.showAlert = function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            ${escapeHtml(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alertDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    };
    
    // Ensure the function is available globally
    if (!window.showNotification) {
        console.error('Failed to create global showNotification function');
    }
})();