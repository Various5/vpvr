/**
 * UI/UX Improvements for IPTV PVR
 * Handles error messages, empty states, loading states, and accessibility
 */

(function() {
    'use strict';

    // ===== ERROR HANDLING =====
    
    /**
     * Display user-friendly error messages
     */
    window.showError = function(message, details = null, container = null) {
        // Validate container is a valid DOM element
        if (container && typeof container === 'object' && container.nodeType === 1) {
            const errorHtml = `
                <div class="error-message animate__animated animate__fadeIn" role="alert">
                    <div class="d-flex align-items-start">
                        <i class="bi bi-exclamation-triangle-fill text-danger me-3 fs-4"></i>
                        <div class="flex-grow-1">
                            <div class="fw-semibold">${escapeHtml(message)}</div>
                            ${details ? `<div class="error-details mt-1">${escapeHtml(details)}</div>` : ''}
                        </div>
                        <button type="button" class="btn-close" aria-label="Close" onclick="this.closest('.error-message').remove()"></button>
                    </div>
                </div>
            `;
            
            try {
                container.insertAdjacentHTML('afterbegin', errorHtml);
            } catch (e) {
                console.error('Failed to insert error into container:', e);
                showNotification(message, 'error', details);
            }
        } else {
            // Use notification system if no valid container
            showNotification(message, 'error', details);
        }
    };

    /**
     * Handle API errors gracefully
     */
    window.handleApiError = function(error, options = {}) {
        // Better error logging
        if (error instanceof Error) {
            console.error('API Error:', error.message, error.stack);
        } else if (error && typeof error === 'object') {
            console.error('API Error:', JSON.stringify(error, null, 2));
        } else {
            console.error('API Error:', error);
        }
        
        const container = options.container || options;  // Support old API
        let message = 'Something went wrong. Please try again.';
        let details = null;
        
        if (error && error.response) {
            // Server responded with error (axios or our custom format)
            const status = error.response.status;
            switch (status) {
                case 400:
                    message = 'Invalid request. Please check your input.';
                    break;
                case 401:
                    message = 'You need to log in to continue.';
                    window.location.href = '/login';
                    return;
                case 403:
                    message = 'You don\'t have permission to do this.';
                    break;
                case 404:
                    message = 'The requested resource was not found.';
                    break;
                case 429:
                    message = 'Too many requests. Please slow down.';
                    break;
                case 500:
                    message = 'Server error. We\'re working on it!';
                    break;
                case 503:
                    message = 'Service temporarily unavailable. Please try again later.';
                    break;
            }
            
            if (error.response.data) {
                if (typeof error.response.data === 'string') {
                    details = error.response.data;
                } else if (error.response.data.detail) {
                    details = error.response.data.detail;
                } else if (error.response.data.message) {
                    details = error.response.data.message;
                }
            }
        } else if (error && error.request) {
            // Request made but no response (axios)
            message = 'Cannot connect to server. Please check your internet connection.';
        } else if (error instanceof Error) {
            // Generic JavaScript error
            message = error.message || 'An unexpected error occurred.';
            details = error.stack;
        }
        
        showError(message, details, container);
        
        // If error system is available, also log to error console
        if (window.errorSystem && window.errorSystem.handleError) {
            window.errorSystem.handleError({
                category: options.category || 'API',
                severity: 'error',
                message: message,
                user_message: message,
                technical_details: details,
                error_code: error.response?.status,
                retry: options.retry
            });
        }
    };

    // ===== EMPTY STATES =====
    
    /**
     * Show empty state with appropriate messaging
     */
    window.showEmptyState = function(container, type = 'default', customMessage = null) {
        const emptyStates = {
            'channels': {
                icon: '📺',
                title: 'No Channels Yet',
                message: 'Start by importing your M3U playlist to add channels.',
                action: '<a href="/admin/imports" class="btn btn-primary"><i class="bi bi-plus-lg"></i> Import Channels</a>'
            },
            'recordings': {
                icon: '📹',
                title: 'No Recordings',
                message: 'You haven\'t recorded anything yet. Schedule a recording from the EPG.',
                action: '<a href="/epg" class="btn btn-primary"><i class="bi bi-calendar"></i> View EPG</a>'
            },
            'epg': {
                icon: '📅',
                title: 'No Program Guide',
                message: 'EPG data is not available. Import an EPG source to see program information.',
                action: '<a href="/admin/imports" class="btn btn-primary"><i class="bi bi-download"></i> Import EPG</a>'
            },
            'search': {
                icon: '🔍',
                title: 'No Results Found',
                message: customMessage || 'Try adjusting your search terms or filters.',
                action: ''
            },
            'error': {
                icon: '⚠️',
                title: 'Something Went Wrong',
                message: customMessage || 'We encountered an error loading this content.',
                action: '<button class="btn btn-primary" onclick="location.reload()"><i class="bi bi-arrow-clockwise"></i> Retry</button>'
            },
            'default': {
                icon: '📭',
                title: 'Nothing Here',
                message: customMessage || 'This area is empty right now.',
                action: ''
            }
        };
        
        const state = emptyStates[type] || emptyStates['default'];
        
        const emptyHtml = `
            <div class="empty-state">
                <div class="empty-state-icon">${state.icon}</div>
                <h3 class="empty-state-title">${state.title}</h3>
                <p class="empty-state-message">${state.message}</p>
                ${state.action ? `<div class="empty-state-action">${state.action}</div>` : ''}
            </div>
        `;
        
        if (container) {
            container.innerHTML = emptyHtml;
        }
    };

    // ===== LOADING STATES =====
    
    /**
     * Show loading spinner
     */
    window.showLoading = function(container, message = 'Loading...') {
        const loadingHtml = `
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <div class="loading-text">${escapeHtml(message)}</div>
            </div>
        `;
        
        if (container) {
            container.innerHTML = loadingHtml;
        }
    };

    /**
     * Show skeleton loader
     */
    window.showSkeleton = function(container, count = 3) {
        let skeletonHtml = '<div class="skeleton-loader">';
        
        for (let i = 0; i < count; i++) {
            skeletonHtml += `
                <div class="card mb-3">
                    <div class="card-body">
                        <div class="skeleton skeleton-title"></div>
                        <div class="skeleton skeleton-text"></div>
                        <div class="skeleton skeleton-text" style="width: 80%"></div>
                    </div>
                </div>
            `;
        }
        
        skeletonHtml += '</div>';
        
        if (container) {
            container.innerHTML = skeletonHtml;
        }
    };

    // ===== NOTIFICATIONS =====
    
    /**
     * Note: showNotification is provided by notification-system.js
     * This ensures it's available even if that script hasn't loaded yet
     */
    if (typeof window.showNotification === 'undefined') {
        console.warn('showNotification not found, notification-system.js may not be loaded');
        // Provide a basic fallback
        window.showNotification = function(message, type = 'info') {
            alert(`${type.toUpperCase()}: ${message}`);
        };
    }

    // ===== ACCESSIBILITY IMPROVEMENTS =====
    
    /**
     * Announce to screen readers
     */
    window.announceToScreenReader = function(message, priority = 'polite') {
        const announcement = document.createElement('div');
        announcement.setAttribute('role', 'status');
        announcement.setAttribute('aria-live', priority);
        announcement.className = 'sr-only';
        announcement.textContent = message;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            announcement.remove();
        }, 1000);
    };

    /**
     * Setup keyboard navigation
     */
    function setupKeyboardNavigation() {
        // Add keyboard event listeners
        document.addEventListener('keydown', (e) => {
            // Escape key closes modals
            if (e.key === 'Escape') {
                const modal = document.querySelector('.modal.show');
                if (modal) {
                    bootstrap.Modal.getInstance(modal)?.hide();
                }
            }
            
            // Slash key focuses search
            if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
                const searchInput = document.querySelector('input[type="search"], #searchInput');
                if (searchInput && document.activeElement !== searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                }
            }
        });
        
        // Add skip link
        const skipLink = document.createElement('a');
        skipLink.href = '#main-content';
        skipLink.className = 'skip-link';
        skipLink.textContent = 'Skip to main content';
        document.body.insertBefore(skipLink, document.body.firstChild);
        
        // Ensure main content has ID
        const mainContent = document.querySelector('main, [role="main"], .container');
        if (mainContent && !mainContent.id) {
            mainContent.id = 'main-content';
        }
    }

    // ===== UTILITY FUNCTIONS =====
    
    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    /**
     * Debounce function for performance
     */
    window.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Format relative time
     */
    window.formatRelativeTime = function(date) {
        const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
        const daysDiff = Math.round((date - new Date()) / (1000 * 60 * 60 * 24));
        
        if (Math.abs(daysDiff) < 1) {
            const hoursDiff = Math.round((date - new Date()) / (1000 * 60 * 60));
            if (Math.abs(hoursDiff) < 1) {
                const minutesDiff = Math.round((date - new Date()) / (1000 * 60));
                return rtf.format(minutesDiff, 'minute');
            }
            return rtf.format(hoursDiff, 'hour');
        }
        
        return rtf.format(daysDiff, 'day');
    };

    // ===== INITIALIZE =====
    
    document.addEventListener('DOMContentLoaded', () => {
        setupKeyboardNavigation();
        
        // Add loading states to forms
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn && !submitBtn.disabled) {
                    submitBtn.disabled = true;
                    const originalText = submitBtn.textContent;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';
                    
                    // Re-enable after 10 seconds (fallback)
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                    }, 10000);
                }
            });
        });
        
        // Improve focus visibility
        document.body.addEventListener('mousedown', () => {
            document.body.classList.add('using-mouse');
        });
        
        document.body.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                document.body.classList.remove('using-mouse');
            }
        });
    });

    // ===== GLOBAL ERROR HANDLER =====
    
    window.addEventListener('error', (e) => {
        console.error('Global error:', e.error);
        showNotification('An unexpected error occurred', 'error', e.error?.message);
    });

    window.addEventListener('unhandledrejection', (e) => {
        console.error('Unhandled promise rejection:', e.reason);
        if (e.reason?.response) {
            handleApiError(e.reason);
        } else {
            showNotification('An unexpected error occurred', 'error', e.reason?.message);
        }
    });

})();