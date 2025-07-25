// Global app functions

// Check if user is logged in
function checkAuth() {
    const token = localStorage.getItem('token');
    const publicPaths = ['/', '/login', '/register'];
    const isPublicPath = publicPaths.includes(window.location.pathname);
    
    // Only redirect to login if on a protected page without token
    if (!token && !isPublicPath) {
        window.location.href = '/login';
    }
}

// Logout function
async function logout() {
    try {
        await axios.post('/api/auth/logout', {}, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    localStorage.removeItem('token');
    window.location.href = '/login';
}

// Clear cache function
function clearCache() {
    if (confirm('Clear all cached data? This will refresh the page.')) {
        // Clear localStorage
        const themeToKeep = localStorage.getItem('theme');
        const tokenToKeep = localStorage.getItem('token');
        const autoSwitchToKeep = localStorage.getItem('autoSwitchBackground');
        const switchIntervalToKeep = localStorage.getItem('backgroundSwitchInterval');
        
        localStorage.clear();
        
        // Restore essential items
        if (themeToKeep) localStorage.setItem('theme', themeToKeep);
        if (tokenToKeep) localStorage.setItem('token', tokenToKeep);
        if (autoSwitchToKeep) localStorage.setItem('autoSwitchBackground', autoSwitchToKeep);
        if (switchIntervalToKeep) localStorage.setItem('backgroundSwitchInterval', switchIntervalToKeep);
        
        // Clear sessionStorage
        sessionStorage.clear();
        
        // Clear browser caches if possible
        if ('caches' in window) {
            caches.keys().then(function(names) {
                for (let name of names) {
                    caches.delete(name);
                }
            });
        }
        
        // Show notification
        if (window.showNotification) {
            showNotification('Cache cleared successfully!', 'success');
        }
        
        // Reload the page after a short delay
        setTimeout(() => {
            window.location.reload(true);
        }, 1000);
    }
}

// Setup axios defaults
axios.defaults.headers.common['Authorization'] = `Bearer ${localStorage.getItem('token')}`;

// Handle 401 errors globally
axios.interceptors.response.use(
    response => response,
    error => {
        if (error.response?.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
        // Log the error but don't reject if it's already handled
        console.error('Axios error:', error);
        return Promise.reject(error);
    }
);

// Global promise rejection handler
window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
    // Prevent the default handler
    event.preventDefault();
});

// Format file size
function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Format duration
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

// Note: showNotification is now provided by notification-system.js
// This is just a fallback if that script hasn't loaded yet
if (typeof window.showNotification === 'undefined') {
    window.showNotification = function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    };
}

// Load current user info
async function loadCurrentUser() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    
    try {
        const response = await axios.get('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const user = response.data;
        
        // Store user ID for WebSocket connection
        localStorage.setItem('user_id', user.id);
        
        // Show user menu items
        document.getElementById('creditsItem').style.display = 'block';
        document.getElementById('userMenu').style.display = 'block';
        document.getElementById('loginLink').style.display = 'none';
        
        // Show/hide admin menu based on role
        if (user.role === 'admin' || user.role === 'manager') {
            const adminMenu = document.getElementById('adminMenu');
            if (adminMenu) {
                adminMenu.style.display = 'block';
            }
        }
        
        // Update user info display
        document.getElementById('user-credits').textContent = user.credits;
        document.getElementById('username-display').textContent = user.username;
        
        return user;
    } catch (error) {
        console.error('Failed to load user info:', error);
        // Hide user menu items on error
        document.getElementById('creditsItem').style.display = 'none';
        document.getElementById('userMenu').style.display = 'none';
        document.getElementById('loginLink').style.display = 'block';
        return null;
    }
}

// Theme initialization is now handled by theme-system.js

// Check auth on page load
document.addEventListener('DOMContentLoaded', async () => {
    checkAuth();
    await loadCurrentUser();
    
    // Update auth UI state
    updateAuthUI();
    
    // Initialize visual effects state
    const visualEffectsEnabled = localStorage.getItem('visualEffects') !== 'false';
    if (!visualEffectsEnabled) {
        document.body.classList.add('no-effects');
    }
});

// Update UI based on authentication state
function updateAuthUI() {
    const token = localStorage.getItem('token');
    const publicPaths = ['/', '/login', '/register'];
    const isPublicPath = publicPaths.includes(window.location.pathname);
    
    if (!token) {
        // User is not authenticated
        document.getElementById('creditsItem').style.display = 'none';
        document.getElementById('userMenu').style.display = 'none';
        document.getElementById('adminMenu').style.display = 'none';
        document.getElementById('loginLink').style.display = 'block';
        
        // Hide navigation items that require auth
        const authRequiredItems = document.querySelectorAll('.nav-link[href="/livetv"], .nav-link[href="/channels"], .nav-link[href="/epg"], .nav-link[href="/recordings"]');
        authRequiredItems.forEach(item => {
            item.parentElement.style.display = 'none';
        });
    } else {
        // User is authenticated - show all navigation items
        const authRequiredItems = document.querySelectorAll('.nav-link[href="/livetv"], .nav-link[href="/channels"], .nav-link[href="/epg"], .nav-link[href="/recordings"]');
        authRequiredItems.forEach(item => {
            item.parentElement.style.display = 'block';
        });
    }
}