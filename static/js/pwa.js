// Store the client's timezone offset in minutes so the server can serve timezone-corrected dates
const timezoneOffset = new Date().getTimezoneOffset();
document.cookie = `timezone_offset=${timezoneOffset}; path=/; max-age=31536000; SameSite=Lax`;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then((registration) => {
        console.log('ServiceWorker registration successful with scope: ', registration.scope);
      })
      .catch((err) => {
        console.log('ServiceWorker registration failed: ', err);
      });
  });
}

// ================= PWA MOBILE INSTALLER SYSTEM =================
(function() {
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || (window.innerWidth <= 768);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    
    // Only run on mobile devices that are not already running standalone
    if (!isMobile || isStandalone) {
        return;
    }

    let deferredPrompt = null;
    let beforeInstallPromptFired = false;

    // Helper functions for localStorage 7-day dismissal state
    const isDismissed = () => {
        const dismissedTime = localStorage.getItem('pwa_install_dismissed');
        if (!dismissedTime) return false;
        const diff = Date.now() - parseInt(dismissedTime, 10);
        const sevenDays = 7 * 24 * 60 * 60 * 1000;
        return diff < sevenDays;
    };

    const recordDismissal = () => {
        localStorage.setItem('pwa_install_dismissed', Date.now().toString());
    };

    const isShownThisSession = () => {
        return sessionStorage.getItem('pwa_install_session_shown') === 'true';
    };

    const markShownThisSession = () => {
        sessionStorage.setItem('pwa_install_session_shown', 'true');
    };

    // UI Helpers
    const showInstallSheet = (type) => {
        const container = document.getElementById('pwa-install-container');
        const actionPrompt = document.getElementById('pwaActionPrompt');
        const iosInstructions = document.getElementById('pwaIosInstructions');
        const androidInstructions = document.getElementById('pwaAndroidInstructions');
        const floatingBtn = document.getElementById('pwaFloatingBtn');

        if (!container) return;

        // Hide all instruction views first
        actionPrompt.style.display = 'none';
        iosInstructions.style.display = 'none';
        androidInstructions.style.display = 'none';

        if (type === 'native') {
            actionPrompt.style.display = 'flex';
        } else if (type === 'ios') {
            iosInstructions.style.display = 'block';
        } else if (type === 'android-fallback') {
            androidInstructions.style.display = 'block';
            
            // Detect browser to display specific guide
            const ua = navigator.userAgent.toLowerCase();
            const chromeGuide = document.getElementById('androidChromeFallback');
            const samsungGuide = document.getElementById('androidSamsungFallback');

            if (chromeGuide && samsungGuide) {
                if (ua.includes('samsungbrowser')) {
                    samsungGuide.style.display = 'block';
                    chromeGuide.style.display = 'none';
                } else {
                    chromeGuide.style.display = 'block';
                    samsungGuide.style.display = 'none';
                }
            }
        }

        container.classList.add('active');
        markShownThisSession();

        // Hide the floating trigger button while sheet is open
        if (floatingBtn) {
            floatingBtn.style.opacity = '0';
            setTimeout(() => { floatingBtn.style.display = 'none'; }, 300);
        }
    };

    const hideInstallSheet = () => {
        const container = document.getElementById('pwa-install-container');
        const floatingBtn = document.getElementById('pwaFloatingBtn');

        if (container) {
            container.classList.remove('active');
        }

        // Show floating install button again
        if (floatingBtn) {
            floatingBtn.style.display = 'flex';
            setTimeout(() => { floatingBtn.style.opacity = '1'; }, 50);
        }
    };

    const showSuccessToast = () => {
        const toast = document.getElementById('pwaToast');
        if (toast) {
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
            }, 4000);
        }
    };

    // 1. Listen for beforeinstallprompt event (Chromium)
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        beforeInstallPromptFired = true;

        // Automatically show installer UI on page load if not dismissed and not shown this session
        if (!isDismissed() && !isShownThisSession()) {
            setTimeout(() => {
                showInstallSheet('native');
            }, 2000);
        } else {
            // Show the floating button so they can still trigger manually
            const floatingBtn = document.getElementById('pwaFloatingBtn');
            if (floatingBtn) {
                floatingBtn.style.display = 'flex';
                setTimeout(() => { floatingBtn.style.opacity = '1'; }, 50);
            }
        }
    });

    // 2. Delayed detection for Safari (iOS) and Android fallback browsers
    window.addEventListener('load', () => {
        setTimeout(() => {
            if (beforeInstallPromptFired) return; // Handled by native prompt listener

            const ua = navigator.userAgent.toLowerCase();
            const isIOS = /ipad|iphone|ipod/.test(ua) && !window.MSStream;

            if (isIOS) {
                // Auto show iOS instructions sheet if not dismissed
                if (!isDismissed() && !isShownThisSession()) {
                    showInstallSheet('ios');
                } else {
                    // Show floating install button to trigger iOS instructions
                    const floatingBtn = document.getElementById('pwaFloatingBtn');
                    if (floatingBtn) {
                        floatingBtn.style.display = 'flex';
                        setTimeout(() => { floatingBtn.style.opacity = '1'; }, 50);
                    }
                }
            } else if (ua.includes('android')) {
                // Auto show Android fallback instructions if not dismissed
                if (!isDismissed() && !isShownThisSession()) {
                    showInstallSheet('android-fallback');
                } else {
                    // Show floating install button to trigger Android instructions
                    const floatingBtn = document.getElementById('pwaFloatingBtn');
                    if (floatingBtn) {
                        floatingBtn.style.display = 'flex';
                        setTimeout(() => { floatingBtn.style.opacity = '1'; }, 50);
                    }
                }
            }
        }, 3000);
    });

    // 3. Track successful installation
    window.addEventListener('appinstalled', () => {
        deferredPrompt = null;
        hideInstallSheet();
        
        // Hide floating button permanently
        const floatingBtn = document.getElementById('pwaFloatingBtn');
        if (floatingBtn) {
            floatingBtn.style.display = 'none';
        }
        
        showSuccessToast();
    });

    // 4. Attach click handlers when DOM loads
    const initHandlers = () => {
        const installBtn = document.getElementById('pwaInstallBtn');
        const cancelBtn = document.getElementById('pwaCancelBtn');
        const overlay = document.getElementById('pwaOverlay');
        const iosCloseBtn = document.getElementById('pwaIosCloseBtn');
        const androidCloseBtn = document.getElementById('pwaAndroidCloseBtn');
        const floatingBtn = document.getElementById('pwaFloatingBtn');

        if (installBtn) {
            installBtn.addEventListener('click', async () => {
                if (!deferredPrompt) return;
                
                // Show browser installation dialog
                deferredPrompt.prompt();
                
                const { outcome } = await deferredPrompt.userChoice;
                if (outcome === 'accepted') {
                    console.log('User accepted the PWA install prompt');
                } else {
                    console.log('User dismissed the PWA install prompt');
                }
                
                deferredPrompt = null;
                hideInstallSheet();
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                recordDismissal();
                hideInstallSheet();
            });
        }

        if (overlay) {
            overlay.addEventListener('click', () => {
                hideInstallSheet();
            });
        }

        if (iosCloseBtn) {
            iosCloseBtn.addEventListener('click', () => {
                recordDismissal();
                hideInstallSheet();
            });
        }

        if (androidCloseBtn) {
            androidCloseBtn.addEventListener('click', () => {
                recordDismissal();
                hideInstallSheet();
            });
        }

        if (floatingBtn) {
            floatingBtn.addEventListener('click', () => {
                if (deferredPrompt) {
                    showInstallSheet('native');
                } else {
                    const ua = navigator.userAgent.toLowerCase();
                    const isIOS = /ipad|iphone|ipod/.test(ua) && !window.MSStream;
                    if (isIOS) {
                        showInstallSheet('ios');
                    } else {
                        showInstallSheet('android-fallback');
                    }
                }
            });
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHandlers);
    } else {
        initHandlers();
    }
})();
