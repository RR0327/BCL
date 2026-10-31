/**
 * Global Theme Engine for IELTS Mock Test Platform & Django Admin
 * Supports explicit 'light' and 'dark' modes.
 * Synchronizes across multiple browser tabs, Django Admin, and candidate pages without FOUC.
 */
(function() {
    "use strict";

    var THEME_KEY = "test-theme";
    var DJANGO_THEME_KEY = "theme";

    var THEME_ICONS = {
        light: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="theme-icon sun-icon" style="color:#f59e0b;"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>',
        dark: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="theme-icon moon-icon" style="color:#818cf8;"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>',
    };

    var THEME_LABELS = {
        light: { title: "Theme: Light (click for Dark)", aria: "Theme mode: Light. Click to switch to Dark mode." },
        dark: { title: "Dark theme (click for Light)", aria: "Dark theme. Click to switch to Light theme." }
    };

    function getStoredTheme() {
        try {
            var val = localStorage.getItem(THEME_KEY);
            if (!val) {
                var dj = localStorage.getItem(DJANGO_THEME_KEY);
                if (dj === "dark" || dj === "light") val = dj;
            }
            return val === "dark" ? "dark" : "light";
        } catch (e) {
            return "light";
        }
    }

    function setStoredTheme(next) {
        try {
            localStorage.setItem(THEME_KEY, next);
            localStorage.setItem(DJANGO_THEME_KEY, next);
        } catch (e) {
            console.warn("Could not save theme to localStorage", e);
        }
    }

    function isEffectiveDark(theme) {
        if (theme === "dark") return true;
        return false;
    }

    function applyThemeToDOM(theme) {
        var dark = isEffectiveDark(theme);
        var root = document.documentElement;
        var body = document.body;
        if (dark) {
            root.classList.add("dark");
            root.setAttribute("data-theme", "dark");
            root.dataset.theme = "dark";
            if (body) {
                body.classList.add("dark");
                body.setAttribute("data-theme", "dark");
            }
        } else {
            root.classList.remove("dark");
            root.setAttribute("data-theme", "light");
            root.dataset.theme = "light";
            if (body) {
                body.classList.remove("dark");
                body.setAttribute("data-theme", "light");
            }
        }

        // Update all toggle buttons on the page
        var buttons = document.querySelectorAll("#themeToggleBtn, .theme-toggle-btn, [data-theme-toggle]");
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            btn.innerHTML = THEME_ICONS[theme];
            var meta = THEME_LABELS[theme];
            btn.title = meta.title;
            btn.setAttribute("aria-label", meta.aria);
        }
    }

    function setNextTheme() {
        var current = getStoredTheme();
        var next = current === "light" ? "dark" : "light";
        setStoredTheme(next);
        applyThemeToDOM(next);
        return next;
    }

    // Initialize immediate state (if not already applied by head script)
    var currentTheme = getStoredTheme();
    applyThemeToDOM(currentTheme);

    // Bind buttons when DOM is loaded
    function bindTogglers() {
        var buttons = document.querySelectorAll("#themeToggleBtn, .theme-toggle-btn, [data-theme-toggle]");
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            if (!btn.__themeBound) {
                btn.__themeBound = true;
                btn.addEventListener("click", function(e) {
                    e.preventDefault();
                    setNextTheme();
                });
            }
        }

        // Synchronize with Django's built-in .theme-toggle buttons if present
        var djButtons = document.querySelectorAll(".theme-toggle");
        for (var j = 0; j < djButtons.length; j++) {
            var djBtn = djButtons[j];
            if (!djBtn.__djSyncBound) {
                djBtn.__djSyncBound = true;
                djBtn.addEventListener("click", function() {
                    setTimeout(function() {
                        var dj = localStorage.getItem(DJANGO_THEME_KEY);
                        var mapped = dj === "dark" ? "dark" : "light";
                        try {
                            localStorage.setItem(THEME_KEY, mapped);
                        } catch (e) {}
                        applyThemeToDOM(mapped);
                    }, 50);
                });
            }
        }

        applyThemeToDOM(getStoredTheme());
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bindTogglers);
    } else {
        bindTogglers();
    }

    // Multi-tab sync via storage events (syncs test-theme and Django theme)
    window.addEventListener("storage", function(e) {
        if (e.key === THEME_KEY || e.key === DJANGO_THEME_KEY) {
            applyThemeToDOM(getStoredTheme());
        }
    });

    // Expose globally
    window.ThemeEngine = {
        getTheme: getStoredTheme,
        setTheme: function(theme) {
            theme = theme === "dark" ? "dark" : "light";
            setStoredTheme(theme);
            applyThemeToDOM(theme);
        },
        toggle: setNextTheme,
        apply: applyThemeToDOM
    };
})();
