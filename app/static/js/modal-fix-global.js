// Global Modal Fix for Bootstrap 5
// This fixes the backdrop overlay issue across the entire application

(function() {
    'use strict';
    
    // Wait for Bootstrap to be loaded
    function initModalFix() {
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal) {
            setTimeout(initModalFix, 100);
            return;
        }
        
        // Override Bootstrap Modal show method
        const originalShow = bootstrap.Modal.prototype.show;
        bootstrap.Modal.prototype.show = function() {
            // Clean up any existing backdrops before showing new modal
            const existingBackdrops = document.querySelectorAll('.modal-backdrop');
            existingBackdrops.forEach(backdrop => backdrop.remove());
            
            // Reset body state
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.body.style.removeProperty('padding-right');
            
            // Call original show method
            originalShow.call(this);
            
            // Force z-index after modal is shown
            setTimeout(() => {
                const backdrop = document.querySelector('.modal-backdrop');
                const modal = this._element;
                
                if (backdrop) {
                    backdrop.style.zIndex = '1040';
                    backdrop.style.position = 'fixed';
                }
                
                if (modal) {
                    modal.style.zIndex = '1050';
                    modal.style.position = 'fixed';
                    
                    const dialog = modal.querySelector('.modal-dialog');
                    if (dialog) {
                        dialog.style.zIndex = '1060';
                        dialog.style.position = 'relative';
                    }
                }
            }, 10);
        };
        
        // Override Bootstrap Modal hide method
        const originalHide = bootstrap.Modal.prototype.hide;
        bootstrap.Modal.prototype.hide = function() {
            originalHide.call(this);
            
            // Extra cleanup after hide
            setTimeout(() => {
                // Remove any lingering backdrops
                document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove());
                
                // Check if any modals are still open
                const openModals = document.querySelectorAll('.modal.show');
                if (openModals.length === 0) {
                    document.body.classList.remove('modal-open');
                    document.body.style.removeProperty('overflow');
                    document.body.style.removeProperty('padding-right');
                }
            }, 300); // After transition completes
        };
    }
    
    // Listen for modal events globally
    document.addEventListener('show.bs.modal', function(e) {
        // Clean state before showing
        const backdrops = document.querySelectorAll('.modal-backdrop');
        if (backdrops.length > 0) {
            console.warn('Found existing backdrop(s), cleaning up...');
            backdrops.forEach(backdrop => backdrop.remove());
        }
    });
    
    document.addEventListener('shown.bs.modal', function(e) {
        // Ensure proper z-index after shown
        const modal = e.target;
        const backdrop = document.querySelector('.modal-backdrop');
        
        if (backdrop && modal) {
            // Force z-index values
            backdrop.style.setProperty('z-index', '1040', 'important');
            modal.style.setProperty('z-index', '1050', 'important');
            
            // Ensure modal content is clickable
            const modalDialog = modal.querySelector('.modal-dialog');
            const modalContent = modal.querySelector('.modal-content');
            
            if (modalDialog) {
                modalDialog.style.setProperty('pointer-events', 'none', 'important');
            }
            
            if (modalContent) {
                modalContent.style.setProperty('pointer-events', 'auto', 'important');
            }
        }
    });
    
    document.addEventListener('hidden.bs.modal', function(e) {
        // Aggressive cleanup after modal is hidden
        setTimeout(() => {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            const openModals = document.querySelectorAll('.modal.show');
            
            // If no modals are open, remove all backdrops
            if (openModals.length === 0) {
                backdrops.forEach(backdrop => backdrop.remove());
                document.body.classList.remove('modal-open');
                document.body.style.removeProperty('overflow');
                document.body.style.removeProperty('padding-right');
            }
        }, 300);
    });
    
    // Initialize the fix
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initModalFix);
    } else {
        initModalFix();
    }
    
    // Also reinitialize on dynamic content
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length > 0) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.classList && node.classList.contains('modal')) {
                        // New modal added to DOM, ensure it's properly handled
                        const modal = bootstrap.Modal.getInstance(node);
                        if (!modal) {
                            // Initialize if not already done
                            new bootstrap.Modal(node);
                        }
                    }
                });
            }
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
})();