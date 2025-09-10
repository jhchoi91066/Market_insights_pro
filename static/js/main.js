/**
 * Market Insights Pro - Enhanced UI Framework
 * Modern dashboard with dark mode, animations, and real-time progress tracking via WebSocket
 */

class MarketInsightsDashboard {
    constructor() {
        this.isSubmitting = false;
        this.darkMode = this.loadThemePreference();
        this.socket = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeTheme();
        this.setupFormHandling();
        this.setupAnimations();
        this.setupNotifications();
    }

    // === WebSocket Management ===
    connectWebSocket() {
        const clientId = Date.now(); // Unique ID for this client session
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${clientId}`;

        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            this.showNotification('🔗 Real-time connection established.', 'success');
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.updateProgress(data);
        };

        this.socket.onclose = () => {
            if (this.isSubmitting) {
                this.showNotification('Connection lost. Please try again.', 'error');
                this.resetFormState();
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket Error:', error);
            this.showNotification('A connection error occurred.', 'error');
            this.resetFormState();
        };
    }

    updateProgress(data) {
        const progressBar = document.getElementById('progress-bar');
        const progressMessage = document.getElementById('progress-message');
        const progressTitle = document.getElementById('progress-title');

        if (progressBar) progressBar.style.width = `${data.progress}%`;
        if (progressMessage) progressMessage.textContent = data.message;

        if (data.status === 'completed') {
            this.isSubmitting = false;
            // Submit the form to navigate to the report page
            document.getElementById('analysisForm').submit();
        } else if (data.status === 'error') {
            this.showNotification(`Error: ${data.message}`, 'error', 5000);
            this.resetFormState();
        }
    }

    // === Theme Management ===
    loadThemePreference() {
        return localStorage.getItem('theme') === 'dark' || 
               (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
    }

    saveThemePreference(isDark) {
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    }

    initializeTheme() {
        this.applyTheme(this.darkMode);
        this.createThemeToggle();
    }

    applyTheme(isDark) {
        document.documentElement.classList.toggle('dark', isDark);
        this.darkMode = isDark;
        this.saveThemePreference(isDark);
    }

    createThemeToggle() {
        const nav = document.querySelector('nav .max-w-7xl > div');
        if (nav && !document.getElementById('themeToggle')) {
            const toggleContainer = document.createElement('div');
            toggleContainer.className = 'flex items-center ml-4';
            toggleContainer.innerHTML = `
                <button id="themeToggle" 
                        class="p-2 rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors duration-200"
                        title="Toggle dark mode (Ctrl+D)">
                    <svg class="w-5 h-5 text-gray-800 dark:text-gray-200 sun-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                    <svg class="w-5 h-5 text-gray-800 dark:text-gray-200 moon-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
                </button>
            `;
            nav.appendChild(toggleContainer);
            
            document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());
            this.updateThemeIcons();
        }
    }

    toggleTheme() {
        this.applyTheme(!this.darkMode);
        this.updateThemeIcons();
        this.showNotification(`Switched to ${this.darkMode ? 'dark' : 'light'} mode`, 'success');
    }

    updateThemeIcons() {
        const sunIcon = document.querySelector('.sun-icon');
        const moonIcon = document.querySelector('.moon-icon');
        if (sunIcon && moonIcon) {
            sunIcon.style.display = this.darkMode ? 'none' : 'block';
            moonIcon.style.display = this.darkMode ? 'block' : 'none';
        }
    }

    // === Form Handling ===
    setupFormHandling() {
        const analysisForm = document.getElementById('analysisForm');
        if (analysisForm) {
            analysisForm.addEventListener('submit', (e) => this.handleFormSubmit(e));
        }
    }

    handleFormSubmit(e) {
        e.preventDefault(); // Prevent normal form submission
        if (this.isSubmitting) {
            this.showNotification('⏳ Analysis already in progress. Please wait...', 'warning');
            return;
        }

        this.isSubmitting = true;
        this.connectWebSocket(); // Establish WebSocket connection
        this.showProgressOverlay();
        this.disableSubmitButton();

        // The form will be submitted programmatically upon 'completed' message from WebSocket
    }

    showProgressOverlay() {
        const loader = document.getElementById('loader');
        if (loader) {
            loader.classList.remove('hidden');
            document.body.classList.add('overflow-hidden');
        }
    }

    disableSubmitButton() {
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = `
                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Analyzing Market Data...
            `;
        }
    }

    resetFormState() {
        this.isSubmitting = false;
        const loader = document.getElementById('loader');
        if (loader) loader.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');

        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = `
                <svg class="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                </svg>
                Start Market Analysis
            `;
        }
    }

    // === Animations & Effects ===
    setupAnimations() {
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) entry.target.classList.add('animate-slide-up');
                });
            }, { threshold: 0.1 });
            document.querySelectorAll('.card, .feature-card, .stat-card').forEach(el => observer.observe(el));
        }
        this.setupHoverEffects();
    }

    setupHoverEffects() {
        document.querySelectorAll('.card').forEach(card => {
            card.addEventListener('mouseenter', () => card.classList.add('shadow-card-hover', 'scale-[1.02]'));
            card.addEventListener('mouseleave', () => card.classList.remove('shadow-card-hover', 'scale-[1.02]'));
        });
        document.querySelectorAll('.btn').forEach(button => {
            button.addEventListener('click', (e) => this.createRippleEffect(e, button));
        });
    }

    createRippleEffect(event, element) {
        const ripple = document.createElement('span');
        const rect = element.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        ripple.style.width = ripple.style.height = `${size}px`;
        ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
        ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
        ripple.className = 'ripple';
        element.style.position = 'relative';
        element.style.overflow = 'hidden';
        element.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    }

    // === Event Listeners ===
    setupEventListeners() {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            if (!localStorage.getItem('theme')) this.applyTheme(e.matches);
        });
        document.addEventListener('keydown', e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
                e.preventDefault();
                this.toggleTheme();
            }
            if (e.key === 'Escape') this.closeOverlays();
        });
    }

    closeOverlays() {
        if (!this.isSubmitting) this.resetFormState();
    }

    // === Notifications ===
    setupNotifications() {
        if (!document.getElementById('notification-container')) {
            const container = document.createElement('div');
            container.id = 'notification-container';
            container.className = 'fixed top-4 right-4 z-50 space-y-2';
            document.body.appendChild(container);
        }
    }

    showNotification(message, type = 'info', duration = 3000) {
        const container = document.getElementById('notification-container');
        if (!container) return;

        const notification = document.createElement('div');
        const typeClasses = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };
        notification.className = `text-white px-4 py-3 rounded-lg shadow-lg transform translate-x-full transition-transform duration-300 max-w-sm ${typeClasses[type]}`;
        notification.innerHTML = `<div class="flex items-center space-x-2"><span class="flex-1">${message}</span><button class="ml-2 hover:opacity-75" onclick="this.parentElement.parentElement.remove()">&times;</button></div>`;
        container.appendChild(notification);

        setTimeout(() => notification.classList.remove('translate-x-full'), 10);
        setTimeout(() => {
            notification.classList.add('translate-x-full');
            setTimeout(() => notification.remove(), 300);
        }, duration);
    }
}

// === Global Initialization ===
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new MarketInsightsDashboard();
    console.info('🚀 Market Insights Pro Dashboard initialized with WebSocket support.');
});