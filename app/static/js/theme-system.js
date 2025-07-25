// Theme System v3 - Now with 4 themes including SpaceWars
class ThemeManager {
    constructor() {
        this.themes = [
            { id: 'light', name: 'Light', icon: 'sun', description: 'Clean and bright for daytime use' },
            { id: 'dark', name: 'Dark', icon: 'moon-stars', description: 'Easy on the eyes for night viewing' },
            { id: 'trip', name: 'Trip', icon: 'stars', description: 'Progressive psychedelic experience' },
            { id: 'spacewars', name: 'SpaceWars', icon: 'rocket', description: 'Journey through the cosmos with dynamic effects' }
        ];
        
        this.currentTheme = localStorage.getItem('theme') || 'dark';
        this.init();
    }

    init() {
        // Check visual effects setting
        this.visualEffectsEnabled = localStorage.getItem('visualEffects') !== 'false';
        
        // Apply theme immediately without delay
        this.applyTheme(this.currentTheme, true);
        this.updateVisualEffects();
        
        // Track if we're changing the theme to avoid loops
        this.isChangingTheme = false;
        
        // Listen for theme changes from other tabs
        window.addEventListener('storage', (e) => {
            // Only apply if we didn't just change it ourselves
            if (e.key === 'theme' && e.newValue && !this.isChangingTheme) {
                this.applyTheme(e.newValue, true);
            } else if (e.key === 'visualEffects') {
                this.visualEffectsEnabled = e.newValue !== 'false';
                this.updateVisualEffects();
            }
        });
    }

    applyTheme(themeId, skipAnimation = false) {
        console.log(`[ThemeSystem] applyTheme called with: ${themeId}, current: ${this.currentTheme}`);
        
        // Prevent multiple simultaneous theme changes
        if (this.isChangingTheme) {
            console.log('[ThemeSystem] Already changing theme, skipping');
            return;
        }
        
        const oldTheme = this.currentTheme;
        
        // If theme hasn't changed, do nothing
        if (oldTheme === themeId) {
            console.log('[ThemeSystem] Theme unchanged, skipping');
            return;
        }
        
        // Set flag to prevent loops
        this.isChangingTheme = true;
        
        // Validate theme
        if (!this.themes.find(t => t.id === themeId)) {
            console.warn(`Theme '${themeId}' not found, falling back to 'dark'`);
            themeId = 'dark';
        }
        
        // Clean up previous theme effects
        if (oldTheme === 'trip') {
            document.body.classList.remove('phase-1', 'phase-2', 'phase-3', 'phase-4', 'phase-5');
            if (this.tripPhaseTimers) {
                this.tripPhaseTimers.forEach(timer => clearTimeout(timer));
                this.tripPhaseTimers = [];
            }
        }
        
        // Remove all particle effects
        document.querySelectorAll('.trip-particle, .spacewars-star').forEach(el => el.remove());
        
        // Simply change the data-theme attribute - CSS is already loaded
        document.documentElement.setAttribute('data-theme', themeId);
        
        // Save preference
        this.currentTheme = themeId;
        localStorage.setItem('theme', themeId);
        
        // Reset flag after a small delay
        setTimeout(() => {
            this.isChangingTheme = false;
        }, 50);
        
        // Update UI elements
        this.updateThemeUI();
        
        // Special effects for trip (only if visual effects enabled)
        if (themeId === 'trip' && !skipAnimation && this.visualEffectsEnabled) {
            this.activateTripMode();
        }
        
        // Special effects for spacewars (only if visual effects enabled)
        if (themeId === 'spacewars' && !skipAnimation && this.visualEffectsEnabled) {
            this.activateSpaceWarsMode();
        }
        
        // Dispatch theme change event
        window.dispatchEvent(new CustomEvent('themeChanged', { 
            detail: { oldTheme, newTheme: themeId } 
        }));
    }

    updateThemeUI() {
        // Update theme dropdown if it exists
        const dropdown = document.querySelector('.theme-dropdown');
        if (dropdown) {
            const currentIcon = this.themes.find(t => t.id === this.currentTheme)?.icon || 'palette';
            dropdown.innerHTML = `<i class="bi bi-${currentIcon}"></i>`;
        }
        
        // Update active states in theme menus
        document.querySelectorAll('[data-theme-switch]').forEach(el => {
            el.classList.toggle('active', el.dataset.themeSwitch === this.currentTheme);
        });
    }

    triggerTransition(oldTheme, newTheme) {
        // Removed transitions to prevent flickering
    }

    activateTripMode() {
        // Clear any existing trip phases
        document.body.classList.remove('phase-1', 'phase-2', 'phase-3', 'phase-4', 'phase-5');
        
        // Clear any existing timers
        if (this.tripPhaseTimers) {
            this.tripPhaseTimers.forEach(timer => clearTimeout(timer));
        }
        this.tripPhaseTimers = [];
        
        // Progressive phase activation
        const phases = [
            { class: 'phase-1', delay: 0 },      // Immediate
            { class: 'phase-2', delay: 60000 },  // 60s
            { class: 'phase-3', delay: 120000 }, // 120s
            { class: 'phase-4', delay: 180000 }, // 180s
            { class: 'phase-5', delay: 240000 }  // 240s
        ];
        
        phases.forEach(phase => {
            const timer = setTimeout(() => {
                if (this.currentTheme === 'trip') {
                    document.body.classList.add(phase.class);
                }
            }, phase.delay);
            this.tripPhaseTimers.push(timer);
        });
        
        // Create floating particles for trip theme
        const particleCount = 15;
        const container = document.body;
        
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'trip-particle';
            particle.style.cssText = `
                position: fixed;
                width: ${Math.random() * 10 + 5}px;
                height: ${Math.random() * 10 + 5}px;
                background: ${['#ff66ff', '#66ffff', '#ffff66', '#ff6699'][Math.floor(Math.random() * 4)]};
                border-radius: 50%;
                pointer-events: none;
                z-index: 9999;
                left: ${Math.random() * window.innerWidth}px;
                top: ${window.innerHeight + 20}px;
                opacity: 0.6;
                animation: floatUp ${Math.random() * 3 + 2}s ease-out forwards;
            `;
            
            container.appendChild(particle);
            
            // Remove after animation
            setTimeout(() => particle.remove(), 5000);
        }
        
        // Add floating animation if not exists
        if (!document.getElementById('trip-float-animation')) {
            const style = document.createElement('style');
            style.id = 'trip-float-animation';
            style.textContent = `
                @keyframes floatUp {
                    to {
                        transform: translateY(-${window.innerHeight + 100}px) rotate(360deg);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    activateSpaceWarsMode() {
        // Create shooting stars for spacewars theme
        const starCount = 8;
        const container = document.body;
        
        for (let i = 0; i < starCount; i++) {
            setTimeout(() => {
                const star = document.createElement('div');
                star.className = 'spacewars-star';
                const startX = Math.random() * window.innerWidth;
                const startY = Math.random() * window.innerHeight * 0.5;
                star.style.cssText = `
                    position: fixed;
                    width: 3px;
                    height: 3px;
                    background: white;
                    border-radius: 50%;
                    pointer-events: none;
                    z-index: 9999;
                    left: ${startX}px;
                    top: ${startY}px;
                    box-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff;
                    animation: shootingStar 1.5s linear forwards;
                `;
                
                container.appendChild(star);
                
                // Add trail
                const trail = document.createElement('div');
                trail.style.cssText = `
                    position: fixed;
                    width: 100px;
                    height: 2px;
                    background: linear-gradient(to right, transparent, #00d4ff, transparent);
                    pointer-events: none;
                    z-index: 9998;
                    left: ${startX}px;
                    top: ${startY + 1}px;
                    transform-origin: left center;
                    transform: rotate(${45 + Math.random() * 30}deg);
                    animation: starTrail 1.5s linear forwards;
                `;
                
                container.appendChild(trail);
                
                // Remove after animation
                setTimeout(() => {
                    star.remove();
                    trail.remove();
                }, 1500);
            }, i * 300);
        }
        
        // Add shooting star animation if not exists
        if (!document.getElementById('spacewars-star-animation')) {
            const style = document.createElement('style');
            style.id = 'spacewars-star-animation';
            style.textContent = `
                @keyframes shootingStar {
                    to {
                        transform: translate(300px, 150px);
                        opacity: 0;
                    }
                }
                @keyframes starTrail {
                    to {
                        transform: rotate(${45 + Math.random() * 30}deg) scaleX(0);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }

    getCurrentTheme() {
        return this.themes.find(t => t.id === this.currentTheme);
    }

    getThemes() {
        return this.themes;
    }
    
    updateVisualEffects() {
        if (this.visualEffectsEnabled) {
            document.body.classList.remove('no-effects');
        } else {
            document.body.classList.add('no-effects');
            // Remove any active particle effects
            document.querySelectorAll('.trip-particle, .spacewars-star').forEach(el => el.remove());
        }
    }
    
    toggleVisualEffects(enabled) {
        this.visualEffectsEnabled = enabled;
        localStorage.setItem('visualEffects', enabled);
        this.updateVisualEffects();
        
        // Re-apply theme effects if enabling and on special theme
        if (enabled && (this.currentTheme === 'trip' || this.currentTheme === 'spacewars')) {
            this.applyTheme(this.currentTheme);
        }
    }
    
    clearCacheAndReload() {
        // Show confirmation dialog
        if (confirm('This will clear all cached data and reload the page. Continue?')) {
            // Clear all localStorage
            localStorage.clear();
            
            // Clear sessionStorage
            sessionStorage.clear();
            
            // Clear cookies for this domain
            document.cookie.split(";").forEach(function(c) { 
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
            });
            
            // Clear all caches if available
            if ('caches' in window) {
                caches.keys().then(names => {
                    names.forEach(name => {
                        caches.delete(name);
                    });
                });
            }
            
            // Force reload without cache
            window.location.reload(true);
        }
    }

    // Create theme selector dropdown for navbar
    createThemeDropdown() {
        const currentTheme = this.getCurrentTheme();
        return `
            <div class="dropdown">
                <button class="btn btn-link nav-link dropdown-toggle theme-dropdown" 
                        data-bs-toggle="dropdown" aria-expanded="false" title="Change theme">
                    <i class="bi bi-${currentTheme.icon}"></i>
                </button>
                <ul class="dropdown-menu dropdown-menu-end">
                    ${this.themes.map(theme => `
                        <li>
                            <a class="dropdown-item ${theme.id === this.currentTheme ? 'active' : ''}" 
                               href="#" onclick="themeManager.applyTheme('${theme.id}'); return false;"
                               data-theme-switch="${theme.id}">
                                <i class="bi bi-${theme.icon} me-2"></i>
                                ${theme.name}
                                ${theme.id === this.currentTheme ? '<i class="bi bi-check ms-auto"></i>' : ''}
                            </a>
                        </li>
                    `).join('')}
                    <li><hr class="dropdown-divider"></li>
                    <li>
                        <a class="dropdown-item" href="/themes">
                            <i class="bi bi-palette me-2"></i>
                            Browse All Themes
                        </a>
                    </li>
                    <li><hr class="dropdown-divider"></li>
                    <li>
                        <a class="dropdown-item" href="#" onclick="themeManager.toggleVisualEffects(!themeManager.visualEffectsEnabled); return false;">
                            <i class="bi bi-${this.visualEffectsEnabled ? 'eye-slash' : 'eye'} me-2"></i>
                            ${this.visualEffectsEnabled ? 'Disable' : 'Enable'} Effects
                        </a>
                    </li>
                    <li>
                        <a class="dropdown-item" href="#" onclick="themeManager.clearCacheAndReload(); return false;">
                            <i class="bi bi-arrow-clockwise me-2"></i>
                            Clear Cache & Reload
                        </a>
                    </li>
                </ul>
            </div>
        `;
    }
}

// Initialize theme manager when DOM is ready
let themeManager;

function initThemeManager() {
    console.log('[ThemeSystem] initThemeManager called');
    
    // Check if already initialized
    if (window.themeManager) {
        console.log('[ThemeSystem] Theme manager already exists, skipping init');
        return;
    }
    
    // Set initial theme attribute to prevent flash
    const savedTheme = localStorage.getItem('theme') || 'dark';
    const validThemes = ['light', 'dark', 'trip', 'spacewars'];
    const themeToUse = validThemes.includes(savedTheme) ? savedTheme : 'dark';
    
    console.log(`[ThemeSystem] Initial theme: ${themeToUse}`);
    
    // Set theme attribute immediately to prevent flash of unstyled content
    document.documentElement.setAttribute('data-theme', themeToUse);
    
    // Initialize theme manager
    themeManager = new ThemeManager();
    window.themeManager = themeManager;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeManager);
} else {
    initThemeManager();
}