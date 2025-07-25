// Theme System v3 - Now with 4 themes including SpaceWars
class ThemeManager {
    constructor() {
        this.themes = [
            { id: 'light', name: 'Light', icon: 'sun', description: 'Clean and bright for daytime use' },
            { id: 'dark', name: 'Dark', icon: 'moon-stars', description: 'Easy on the eyes for night viewing' },
            { id: 'spacecake', name: 'Spacecake', icon: 'stars', description: 'A trippy, animated experience' },
            { id: 'spacewars', name: 'SpaceWars', icon: 'rocket', description: 'Journey through the cosmos with dynamic effects' }
        ];
        
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.init();
    }

    init() {
        // Check visual effects setting
        this.visualEffectsEnabled = localStorage.getItem('visualEffects') !== 'false';
        
        // Wait a moment for CSS to be ready, then apply saved theme
        setTimeout(() => {
            this.applyTheme(this.currentTheme, true);
            this.updateVisualEffects();
        }, 100);
        
        // Listen for theme changes from other tabs
        window.addEventListener('storage', (e) => {
            if (e.key === 'theme' && e.newValue) {
                this.applyTheme(e.newValue, true);
            } else if (e.key === 'visualEffects') {
                this.visualEffectsEnabled = e.newValue !== 'false';
                this.updateVisualEffects();
            }
        });
    }

    applyTheme(themeId, skipAnimation = false) {
        const oldTheme = this.currentTheme;
        
        // Validate theme
        if (!this.themes.find(t => t.id === themeId)) {
            console.warn(`Theme '${themeId}' not found, falling back to 'light'`);
            themeId = 'light';
            localStorage.setItem('theme', 'light');
        }
        
        // Update data attribute
        document.documentElement.setAttribute('data-theme', themeId);
        
        // Enable/disable theme CSS files
        this.themes.forEach(theme => {
            const link = document.getElementById(`theme-${theme.id}-css`);
            if (link) {
                link.disabled = theme.id !== themeId;
            }
        });
        
        // Save preference
        this.currentTheme = themeId;
        localStorage.setItem('theme', themeId);
        
        // Update any theme UI elements
        this.updateThemeUI();
        
        // Trigger animation for theme change
        if (!skipAnimation && oldTheme !== themeId) {
            this.triggerTransition(oldTheme, themeId);
        }
        
        // Special effects for spacecake (only if visual effects enabled)
        if (themeId === 'spacecake' && !skipAnimation && this.visualEffectsEnabled) {
            this.activateSpacecakeMode();
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
        // Add transition class
        document.body.style.transition = 'background-color 0.3s ease, color 0.3s ease';
        
        // Remove transition after animation
        setTimeout(() => {
            document.body.style.transition = '';
        }, 300);
    }

    activateSpacecakeMode() {
        // Create floating particles for spacecake theme
        const particleCount = 15;
        const container = document.body;
        
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'spacecake-particle';
            particle.style.cssText = `
                position: fixed;
                width: ${Math.random() * 10 + 5}px;
                height: ${Math.random() * 10 + 5}px;
                background: ${['#ee7752', '#e73c7e', '#23a6d5', '#23d5ab'][Math.floor(Math.random() * 4)]};
                border-radius: 50%;
                pointer-events: none;
                z-index: 9999;
                left: ${Math.random() * window.innerWidth}px;
                top: ${window.innerHeight + 20}px;
                opacity: 0.8;
                animation: floatUp ${Math.random() * 3 + 2}s ease-out forwards;
            `;
            
            container.appendChild(particle);
            
            // Remove after animation
            setTimeout(() => particle.remove(), 5000);
        }
        
        // Add floating animation if not exists
        if (!document.getElementById('spacecake-float-animation')) {
            const style = document.createElement('style');
            style.id = 'spacecake-float-animation';
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
            document.querySelectorAll('.spacecake-particle, .spacewars-star').forEach(el => el.remove());
        }
    }
    
    toggleVisualEffects(enabled) {
        this.visualEffectsEnabled = enabled;
        localStorage.setItem('visualEffects', enabled);
        this.updateVisualEffects();
        
        // Re-apply theme effects if enabling and on special theme
        if (enabled && (this.currentTheme === 'spacecake' || this.currentTheme === 'spacewars')) {
            this.applyTheme(this.currentTheme);
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
                </ul>
            </div>
        `;
    }
}

// Initialize theme manager when DOM is ready
let themeManager;

function initThemeManager() {
    // Set initial theme attribute to prevent flash
    const savedTheme = localStorage.getItem('theme') || 'light';
    const validThemes = ['light', 'dark', 'spacecake', 'spacewars'];
    const themeToUse = validThemes.includes(savedTheme) ? savedTheme : 'light';
    
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