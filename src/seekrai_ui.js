// SeekrAI UI - JavaScript

/* ============================================ */
/* LOGIN PAGE JAVASCRIPT */
/* ============================================ */

// Login form submission handler
function initLoginPage() {
    const loginForm = document.getElementById('loginForm');
    const errorMessage = document.getElementById('errorMessage');

    if (!loginForm) return; // Not on login page

    const toggleBtn = document.getElementById('togglePassword');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const pwdInput = document.getElementById('password');
            const eyeOpen = document.getElementById('eyeOpen');
            const eyeClosed = document.getElementById('eyeClosed');
            const isHidden = pwdInput.type === 'password';
            pwdInput.type = isHidden ? 'text' : 'password';
            eyeOpen.style.display = isHidden ? 'none' : 'block';
            eyeClosed.style.display = isHidden ? 'block' : 'none';
        });
    }

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorMessage.classList.remove('show');

        const formData = new FormData(loginForm);
        const username = formData.get('username')?.trim() || '';
        const password = formData.get('password') || '';

        // Frontend validation
        if (!username) {
            errorMessage.textContent = 'Please enter your Kerberos username';
            errorMessage.classList.add('show');
            return;
        }

        if (!password) {
            errorMessage.textContent = 'Please enter your password';
            errorMessage.classList.add('show');
            return;
        }

        // Basic username format validation (alphanumeric, underscore, dash)
        if (!/^[a-zA-Z0-9_-]+$/.test(username)) {
            errorMessage.textContent = 'Invalid username format. Only letters, numbers, underscore and dash allowed.';
            errorMessage.classList.add('show');
            return;
        }

        // Disable submit button during login
        const submitButton = loginForm.querySelector('button[type="submit"]');
        const originalButtonText = submitButton?.textContent;
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = 'Authenticating...';
        }

        try {
            const response = await fetch('/seekr/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (data.success) {
                // Set login timestamp to track new sessions
                sessionStorage.setItem('loginTimestamp', Date.now().toString());
                window.location.href = data.redirect || '/seekr/main';
            } else {
                errorMessage.textContent = data.message || 'Invalid credentials. Please try again.';
                errorMessage.classList.add('show');
            }
        } catch (error) {
            console.error('Login error:', error);
            errorMessage.textContent = 'Connection error. Please check the server and try again.';
            errorMessage.classList.add('show');
        } finally {
            // Re-enable submit button
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = originalButtonText;
            }
        }
    });
}

// Initialize login page when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLoginPage);
} else {
    initLoginPage();
}

/* ============================================ */
/* MAIN UI JAVASCRIPT */
/* ============================================ */

// Cache for Related Content to avoid re-fetching
const relatedContentCache = {
    ohss: {} // Map of OHSS key -> {kcs_articles: [], slack_threads: []}
};

// Track in-flight requests to prevent duplicate API calls
const inFlightRequests = new Map();

// Fetch and display logged-in user info
async function loadUserInfo() {
    // Only run on main UI page (not on login page)
    const userNameElement = document.getElementById('userName');
    if (!userNameElement) return; // Not on main page, skip

    try {
        const response = await fetch('/api/user');
        if (response.ok) {
            const data = await response.json();
            const username = data.username;
            const email = data.email;

            // Update username display
            userNameElement.textContent = username;

            // Update avatar with first letter of username
            const userAvatarElement = document.getElementById('userAvatar');
            if (userAvatarElement && username) {
                userAvatarElement.textContent = username.charAt(0).toUpperCase();
            }

            // Auto-populate email on settings page
            const emailInput = document.getElementById('atlassianEmail');
            if (emailInput && email) {
                emailInput.value = email;
            }
        } else {
            // Not authenticated, redirect to login
            console.log('User not authenticated, redirecting to login');
            window.location.href = '/seekr/login';
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        // On error, also redirect to login
        window.location.href = '/seekr/login';
    }
}

// Load user info on page load (only runs if userName element exists)
window.addEventListener('DOMContentLoaded', loadUserInfo);

// User menu dropdown toggle
const userMenu = document.getElementById('userMenu');
const userDropdown = document.getElementById('userDropdown');

if (userMenu && userDropdown) {
    // Toggle dropdown on click
    userMenu.addEventListener('click', (e) => {
        e.stopPropagation();
        userMenu.classList.toggle('active');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!userMenu.contains(e.target)) {
            userMenu.classList.remove('active');
        }
    });

    // Prevent dropdown from closing when clicking inside it
    userDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

/* ============================================ */
/* NOTIFICATION DROPDOWN */
/* ============================================ */

// Notification dropdown toggle
const notificationBtn = document.getElementById('notificationBtn');
const notificationDropdown = document.getElementById('notificationDropdown');
const notificationBadge = document.getElementById('notificationBadge');
const notificationList = document.getElementById('notificationList');

// Track viewed notifications in sessionStorage
// Key: notification identifier (e.g., "atlassian_expiring_2026-06-25")
// Value: true if viewed
function getViewedNotifications() {
    // Clear viewed notifications on new login (different session)
    const currentLoginTime = sessionStorage.getItem('loginTimestamp');
    const viewedLoginTime = sessionStorage.getItem('viewedNotificationsLoginTime');

    if (currentLoginTime && currentLoginTime !== viewedLoginTime) {
        // New login session, clear old viewed notifications
        sessionStorage.removeItem('viewedNotifications');
        sessionStorage.setItem('viewedNotificationsLoginTime', currentLoginTime);
        return {};
    }

    const viewed = sessionStorage.getItem('viewedNotifications');
    return viewed ? JSON.parse(viewed) : {};
}

function markNotificationAsViewed(notificationKey) {
    const viewed = getViewedNotifications();
    viewed[notificationKey] = true;
    sessionStorage.setItem('viewedNotifications', JSON.stringify(viewed));
}

function clearViewedNotifications() {
    sessionStorage.removeItem('viewedNotifications');
}

if (notificationBtn && notificationDropdown) {
    // Toggle dropdown on click
    notificationBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        notificationDropdown.classList.toggle('active');

        // When opening dropdown, mark all current notifications as viewed
        // This clears the badge count
        if (notificationDropdown.classList.contains('active')) {
            const currentNotifications = Array.from(document.querySelectorAll('.notification-item'));
            currentNotifications.forEach(item => {
                const key = item.getAttribute('data-notification-key');
                if (key) {
                    markNotificationAsViewed(key);
                }
            });

            // Clear badge immediately when opening dropdown
            if (notificationBadge) {
                notificationBadge.style.display = 'none';
            }
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!notificationBtn.contains(e.target) && !notificationDropdown.contains(e.target)) {
            notificationDropdown.classList.remove('active');
        }
    });
}

// Check for token expiry notifications
async function checkTokenExpiry() {
    try {
        const response = await fetch('/api/settings/token-status');
        if (!response.ok) return;

        const data = await response.json();
        console.log('Token status data:', data);
        const notifications = [];

        // Check Atlassian token
        if (data.atlassian && data.atlassian.revoked) {
            // Token was detected as revoked/expired by 24-hour validation
            notifications.push({
                key: `atlassian_revoked_${data.atlassian.revoked_date}`,
                type: 'warning',
                icon: 'alert',
                title: 'Atlassian Token Revoked or Expired',
                message: `${data.atlassian.revoked_reason}. Please generate a new token.`,
                time: data.atlassian.revoked_date || 'Recently',
                dismissible: true,
                dismissType: 'atlassian_revoked',
                link: '/seekr/settings#atlassian-token-section'
            });
        } else if (data.atlassian && data.atlassian.configured && !data.atlassian.expired) {
            const daysRemaining = data.atlassian.days_remaining;
            if (daysRemaining !== null && daysRemaining <= 7) {
                notifications.push({
                    key: `atlassian_expiring_${data.atlassian.expiry_date}`,
                    type: daysRemaining <= 2 ? 'warning' : 'info',
                    icon: 'clock',
                    title: 'Atlassian Token Expiring Soon',
                    message: `Token expires in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} (${formatDateToMMDDYYYY(data.atlassian.expiry_date)})`,
                    time: 'Now',
                    link: '/seekr/settings#atlassian-token-section'
                });
            }
        }

        // Check Red Hat token
        if (data.redhat && data.redhat.configured && !data.redhat.expired) {
            const daysRemaining = data.redhat.days_remaining;
            if (daysRemaining !== null && daysRemaining <= 7) {
                notifications.push({
                    key: `redhat_expiring_${data.redhat.expiry_date}`,
                    type: daysRemaining <= 2 ? 'warning' : 'info',
                    icon: 'clock',
                    title: 'Red Hat Token Expiring Soon',
                    message: `Token expires in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} (${formatDateToMMDDYYYY(data.redhat.expiry_date)})`,
                    time: 'Now',
                    link: '/seekr/settings#redhat-token-section'
                });
            }
        }

        // Check GitHub token
        if (data.github && data.github.configured && !data.github.expired) {
            const daysRemaining = data.github.days_remaining;
            if (daysRemaining !== null && daysRemaining <= 7) {
                notifications.push({
                    key: `github_expiring_${data.github.expiry_date}`,
                    type: daysRemaining <= 2 ? 'warning' : 'info',
                    icon: 'clock',
                    title: 'GitHub Token Expiring Soon',
                    message: `Token expires in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} (${formatDateToMMDDYYYY(data.github.expiry_date)})`,
                    time: 'Now',
                    link: '/seekr/settings#github-token-section'
                });
            }
        }

        // Check GitLab token
        if (data.gitlab && data.gitlab.configured && !data.gitlab.expired) {
            const daysRemaining = data.gitlab.days_remaining;
            if (daysRemaining !== null && daysRemaining <= 7) {
                notifications.push({
                    key: `gitlab_expiring_${data.gitlab.expiry_date}`,
                    type: daysRemaining <= 2 ? 'warning' : 'info',
                    icon: 'clock',
                    title: 'GitLab Token Expiring Soon',
                    message: `Token expires in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} (${formatDateToMMDDYYYY(data.gitlab.expiry_date)})`,
                    time: 'Now',
                    link: '/seekr/settings#gitlab-token-section'
                });
            }
        }

        // Update badge - only show for UNVIEWED notifications
        console.log('Total notifications:', notifications.length);
        const viewedNotifications = getViewedNotifications();
        const unviewedCount = notifications.filter(n => !viewedNotifications[n.key]).length;
        console.log('Unviewed count:', unviewedCount, 'notifications:', notifications);

        if (unviewedCount > 0) {
            notificationBadge.textContent = unviewedCount;
            notificationBadge.style.display = 'block';
        } else {
            notificationBadge.style.display = 'none';
        }

        // Render notifications
        renderNotifications(notifications);
    } catch (error) {
        console.error('Error checking token expiry:', error);
    }
}

function renderNotifications(notifications) {
    if (!notificationList) return;

    if (notifications.length === 0) {
        notificationList.innerHTML = `
            <div class="notification-empty">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                </svg>
                <p>No notifications</p>
            </div>
        `;
        return;
    }

    notificationList.innerHTML = notifications.map((notif, index) => {
        // Choose icon based on notification type
        let iconSvg = '';
        if (notif.icon === 'alert') {
            iconSvg = `
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            `;
        } else {
            // Default clock icon
            iconSvg = `
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
            `;
        }

        // Add dismiss button for dismissible notifications
        const dismissBtn = notif.dismissible ? `
            <button class="notification-dismiss" data-dismiss-type="${notif.dismissType}" title="Dismiss">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
        ` : '';

        const linkAttr = notif.link ? `data-link="${notif.link}"` : '';
        const clickableClass = notif.link ? 'notification-clickable' : '';
        const notifKeyAttr = notif.key ? `data-notification-key="${notif.key}"` : '';

        return `
            <div class="notification-item ${notif.type} ${clickableClass}" data-notification-index="${index}" ${linkAttr} ${notifKeyAttr}>
                <div class="notification-item-header">
                    <div class="notification-icon ${notif.type}">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            ${iconSvg}
                        </svg>
                    </div>
                    <div class="notification-content">
                        <div class="notification-title">${notif.title}</div>
                        <div class="notification-message">${notif.message}</div>
                        <div class="notification-time">${notif.time}</div>
                    </div>
                    ${dismissBtn}
                </div>
            </div>
        `;
    }).join('');

    // Add event listeners for dismiss buttons
    document.querySelectorAll('.notification-dismiss').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const dismissType = btn.getAttribute('data-dismiss-type');
            await dismissNotification(dismissType);
        });
    });

    // Add event listeners for clickable notifications
    document.querySelectorAll('.notification-clickable').forEach(item => {
        item.addEventListener('click', (e) => {
            // Don't navigate if clicking dismiss button
            if (e.target.closest('.notification-dismiss')) return;

            // Mark this notification as viewed
            const notificationKey = item.getAttribute('data-notification-key');
            if (notificationKey) {
                markNotificationAsViewed(notificationKey);
            }

            // Clear badge immediately (user is going to Settings to fix it)
            if (notificationBadge) {
                notificationBadge.style.display = 'none';
            }

            // Close the notification dropdown before navigating
            if (notificationDropdown) {
                notificationDropdown.classList.remove('active');
            }

            const link = item.getAttribute('data-link');
            if (link) {
                window.location.href = link;
            }
        });
    });
}

async function dismissNotification(type) {
    try {
        const response = await fetch('/api/settings/dismiss-notification', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type })
        });

        if (response.ok) {
            // Refresh notifications
            await checkTokenExpiry();
        }
    } catch (error) {
        console.error('Error dismissing notification:', error);
    }
}

// Check token expiry on page load and every 5 minutes
if (notificationList) {
    checkTokenExpiry();
    setInterval(checkTokenExpiry, 5 * 60 * 1000); // Every 5 minutes
}

/* ============================================ */
/* SETTINGS PAGE JAVASCRIPT */
/* ============================================ */

// Helper function to format dates from YYYY-MM-DD to MM/DD/YYYY
function formatDateToMMDDYYYY(dateString) {
    if (!dateString) return dateString;

    // If already in MM/DD/YYYY format, return as-is
    if (dateString.includes('/')) return dateString;

    // Convert YYYY-MM-DD to MM/DD/YYYY
    const parts = dateString.split('-');
    if (parts.length === 3) {
        const [year, month, day] = parts;
        return `${month}/${day}/${year}`;
    }

    return dateString;
}

// Helper function to convert MM/DD/YYYY back to YYYY-MM-DD for input fields
function formatDateToYYYYMMDD(dateString) {
    if (!dateString) return dateString;

    // If already in YYYY-MM-DD format, return as-is
    if (dateString.includes('-')) return dateString;

    // Convert MM/DD/YYYY to YYYY-MM-DD
    const parts = dateString.split('/');
    if (parts.length === 3) {
        const [month, day, year] = parts;
        return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }

    return dateString;
}

// Toggle password visibility for Atlassian token
const toggleAtlassianTokenBtn = document.getElementById('toggleAtlassianToken');
const atlassianTokenInput = document.getElementById('atlassianToken');

if (toggleAtlassianTokenBtn && atlassianTokenInput) {
    toggleAtlassianTokenBtn.addEventListener('click', () => {
        const type = atlassianTokenInput.type === 'password' ? 'text' : 'password';
        atlassianTokenInput.type = type;

        // Update icon
        const svg = toggleAtlassianTokenBtn.querySelector('svg');
        if (type === 'text') {
            // Eye with slash (hidden)
            svg.innerHTML = `
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
            `;
        } else {
            // Regular eye
            svg.innerHTML = `
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
            `;
        }
    });
}

// Save Atlassian API Token
const saveTokenBtn = document.getElementById('saveTokenBtn');
const statusMessage = document.getElementById('statusMessage');

const atlassianTokenExpiryInput = document.getElementById('atlassianTokenExpiry');
const atlassianEmailInput = document.getElementById('atlassianEmail');

// Set minimum and maximum dates for expiry date picker
function initializeDatePicker() {
    if (!atlassianTokenExpiryInput) return;

    const today = new Date();
    today.setHours(0, 0, 0, 0); // Reset to start of day

    // Format date as YYYY-MM-DD using local timezone (not UTC)
    const formatDate = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

    // Set min to today
    const minDateStr = formatDate(today);
    atlassianTokenExpiryInput.setAttribute('min', minDateStr);

    // Set max to 90 days from today
    const maxDate = new Date(today);
    maxDate.setDate(maxDate.getDate() + 90);
    const maxDateStr = formatDate(maxDate);
    atlassianTokenExpiryInput.setAttribute('max', maxDateStr);

    console.log('Date picker initialized - Min:', minDateStr, 'Max:', maxDateStr);

    // Add validation on input change to enforce the limit
    atlassianTokenExpiryInput.addEventListener('input', function() {
        if (!this.value) return;

        const selectedDate = new Date(this.value);
        selectedDate.setHours(0, 0, 0, 0);

        if (selectedDate < today) {
            this.setCustomValidity('Date cannot be in the past');
            showStatus('error', 'Expiry date cannot be in the past');
            this.value = '';
        } else if (selectedDate > maxDate) {
            this.setCustomValidity('Date cannot be more than 90 days from today');
            showStatus('error', 'Atlassian tokens can last no longer than 90 days');
            this.value = '';
        } else {
            this.setCustomValidity(''); // Clear any previous error
        }
    });
}

// Initialize date picker when DOM is ready
if (atlassianTokenExpiryInput) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeDatePicker);
    } else {
        initializeDatePicker();
    }
}

if (saveTokenBtn && atlassianTokenInput && statusMessage) {
    saveTokenBtn.addEventListener('click', async () => {
        const token = atlassianTokenInput.value.trim();
        const expiryDate = atlassianTokenExpiryInput ? atlassianTokenExpiryInput.value : '';
        const email = atlassianEmailInput ? atlassianEmailInput.value.trim() : '';

        if (!email) { showStatus('error', 'Email not populated. Please refresh the page.'); return; }

        if (!token) {
            showStatus('error', 'Please enter an API token');
            return;
        }

        if (!expiryDate) {
            showStatus('error', 'Please enter the token expiry date that you set on Atlassian');
            return;
        }

        // Validate expiry date is not in the past
        const selectedDate = new Date(expiryDate);
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        if (selectedDate < today) {
            showStatus('error', 'Expiry date cannot be in the past');
            return;
        }

        // Validate expiry date is within 90 days
        const maxDate = new Date();
        maxDate.setDate(maxDate.getDate() + 90);
        if (selectedDate > maxDate) {
            showStatus('error', 'Atlassian tokens can last no longer than 90 days');
            return;
        }

        // Show loading state
        saveTokenBtn.disabled = true;
        saveTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Validating token...
        `;

        try {
            // First, validate the token is actually working
            showStatus('info', 'Validating token with Atlassian API...');

            const testResponse = await fetch('/api/settings/test-atlassian-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token, email })
            });

            const testData = await testResponse.json();

            if (!testResponse.ok) {
                showStatus('error', `Token validation failed: ${testData.message}`);
                saveTokenBtn.disabled = false;
                saveTokenBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                        <polyline points="17 21 17 13 7 13 7 21"/>
                        <polyline points="7 3 7 8 15 8"/>
                    </svg>
                    Save Token
                `;
                return;
            }

            // Token is valid, now save it
            saveTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 6v6l4 2"/>
                </svg>
                Saving...
            `;

            const response = await fetch('/api/settings/atlassian-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    token,
                    email,
                    expiry_date: expiryDate
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Show comprehensive success message
                const formattedDate = formatDateToMMDDYYYY(expiryDate);
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                const expiry = new Date(expiryDate);
                const daysRemaining = Math.ceil((expiry - today) / (1000 * 60 * 60 * 24));

                showStatus('success', `✅ Token validated and saved! Valid for ${daysRemaining} days (expires ${formattedDate})`);
            } else {
                showStatus('error', data.message || 'Failed to save API token');
            }
        } catch (error) {
            showStatus('error', 'An error occurred while saving the token');
        } finally {
            // Restore button
            saveTokenBtn.disabled = false;
            saveTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/>
                    <polyline points="7 3 7 8 15 8"/>
                </svg>
                Save Token
            `;
        }
    });
}

// Test Atlassian API Token Connection
const testTokenBtn = document.getElementById('testTokenBtn');

if (testTokenBtn && atlassianTokenInput && statusMessage) {
    testTokenBtn.addEventListener('click', async () => {
        const token = atlassianTokenInput.value.trim();
        const email = atlassianEmailInput ? atlassianEmailInput.value.trim() : '';

        if (!token) {
            showStatus('error', 'Please enter an API token to test');
            return;
        }

        // Show loading state
        testTokenBtn.disabled = true;
        testTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Testing...
        `;

        try {
            const response = await fetch('/api/settings/test-atlassian-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token, email })
            });

            const data = await response.json();

            if (response.ok) {
                showStatus('success', data.message || 'Connection successful! Token is valid.');
            } else {
                showStatus('error', data.message || 'Connection failed. Please check your token.');
            }
        } catch (error) {
            showStatus('error', 'An error occurred while testing the connection');
        } finally {
            // Restore button
            testTokenBtn.disabled = false;
            testTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                Test Connection
            `;
        }
    });
}

// Helper function to show status messages
function showStatus(type, message) {
    if (!statusMessage) return;

    statusMessage.className = 'status-message show ' + type;
    statusMessage.textContent = message;

    // Auto-hide after 5 seconds
    setTimeout(() => {
        statusMessage.classList.remove('show');
    }, 5000);
}

// Load saved token on page load (full token for verification)
async function loadSavedToken() {
    if (!atlassianTokenInput) return;

    try {
        const response = await fetch('/api/settings/atlassian-token');
        if (response.ok) {
            const data = await response.json();

            // Always populate email (auto-generated from Kerberos username)
            if (data.email && atlassianEmailInput) {
                atlassianEmailInput.value = data.email;
            }

            if (data.expired) {
                showStatus('error', data.message || 'Your Atlassian token has expired or been revoked. Please generate a new one.');
                atlassianTokenInput.value = '';
                // Don't clear email - it's auto-populated from Kerberos
                if (atlassianTokenExpiryInput) atlassianTokenExpiryInput.value = '';
            } else if (data.token) {
                atlassianTokenInput.value = data.token;

                // Load expiry date if available (convert to YYYY-MM-DD for date input)
                if (data.expiry_date && atlassianTokenExpiryInput) {
                    atlassianTokenExpiryInput.value = formatDateToYYYYMMDD(data.expiry_date);
                }
            }
        }
    } catch (error) {
        console.error('Error loading saved token:', error);
    }
}

// Initialize settings page
if (atlassianTokenInput) {
    loadSavedToken();
}

/* ============================================ */
/* RED HAT API TOKEN FUNCTIONALITY */
/* ============================================ */

// Toggle password visibility for Red Hat token
const toggleRedhatTokenBtn = document.getElementById('toggleRedhatToken');
const redhatTokenInput = document.getElementById('redhatToken');

if (toggleRedhatTokenBtn && redhatTokenInput) {
    toggleRedhatTokenBtn.addEventListener('click', () => {
        const type = redhatTokenInput.type === 'password' ? 'text' : 'password';
        redhatTokenInput.type = type;

        // Update icon
        const svg = toggleRedhatTokenBtn.querySelector('svg');
        if (type === 'text') {
            // Eye with slash (hidden)
            svg.innerHTML = `
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
            `;
        } else {
            // Regular eye
            svg.innerHTML = `
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
            `;
        }
    });
}

// Save Red Hat API Token
const saveRedhatTokenBtn = document.getElementById('saveRedhatTokenBtn');
const redhatStatusMessage = document.getElementById('redhatStatusMessage');

if (saveRedhatTokenBtn && redhatTokenInput && redhatStatusMessage) {
    saveRedhatTokenBtn.addEventListener('click', async () => {
        const token = redhatTokenInput.value.trim();

        if (!token) {
            showRedhatStatus('error', 'Please enter an API token');
            return;
        }

        // Show loading state
        saveRedhatTokenBtn.disabled = true;
        saveRedhatTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Saving...
        `;

        try {
            const response = await fetch('/api/settings/redhat-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token })
            });

            const data = await response.json();

            if (response.ok) {
                showRedhatStatus('success', data.message || 'Red Hat API token saved successfully!');
            } else {
                showRedhatStatus('error', data.message || 'Failed to save API token');
            }
        } catch (error) {
            showRedhatStatus('error', 'An error occurred while saving the token');
        } finally {
            // Restore button
            saveRedhatTokenBtn.disabled = false;
            saveRedhatTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/>
                    <polyline points="7 3 7 8 15 8"/>
                </svg>
                Save Token
            `;
        }
    });
}

// Test Red Hat API Token Connection
const testRedhatTokenBtn = document.getElementById('testRedhatTokenBtn');

if (testRedhatTokenBtn && redhatTokenInput && redhatStatusMessage) {
    testRedhatTokenBtn.addEventListener('click', async () => {
        const token = redhatTokenInput.value.trim();

        if (!token) {
            showRedhatStatus('error', 'Please enter an API token to test');
            return;
        }

        // Show loading state
        testRedhatTokenBtn.disabled = true;
        testRedhatTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Testing...
        `;

        try {
            const response = await fetch('/api/settings/test-redhat-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token })
            });

            const data = await response.json();

            if (response.ok) {
                showRedhatStatus('success', data.message || 'Connection successful! Token is valid for SFDC and KCS.');
            } else {
                showRedhatStatus('error', data.message || 'Connection failed. Please check your token.');
            }
        } catch (error) {
            showRedhatStatus('error', 'An error occurred while testing the connection');
        } finally {
            // Restore button
            testRedhatTokenBtn.disabled = false;
            testRedhatTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                Test Connection
            `;
        }
    });
}

// Helper function to show Red Hat status messages
function showRedhatStatus(type, message) {
    if (!redhatStatusMessage) return;

    redhatStatusMessage.className = 'status-message show ' + type;
    redhatStatusMessage.textContent = message;

    // Auto-hide after 5 seconds
    setTimeout(() => {
        redhatStatusMessage.classList.remove('show');
    }, 5000);
}

// Load saved Red Hat token on page load (full token for verification)
async function loadSavedRedhatToken() {
    if (!redhatTokenInput) return;

    try {
        const response = await fetch('/api/settings/redhat-token');
        if (response.ok) {
            const data = await response.json();

            if (data.expired) {
                showRedhatStatus('error', data.message || 'Your Red Hat token has expired (30 days). Please generate a new one.');
                redhatTokenInput.value = '';
            } else if (data.token) {
                redhatTokenInput.value = data.token;

                // Show expiry info if available
                if (data.days_remaining !== undefined && data.days_remaining <= 7) {
                    const warningType = data.days_remaining <= 2 ? 'warning' : 'info';
                    showRedhatStatus(warningType, `Token expires in ${data.days_remaining} days (${formatDateToMMDDYYYY(data.expiry_date)})`);
                }
            }
        }
    } catch (error) {
        console.error('Error loading saved Red Hat token:', error);
    }
}

// Initialize Red Hat token section
if (redhatTokenInput) {
    loadSavedRedhatToken();
}

/* ============================================ */
/* SLACK API TOKENS FUNCTIONALITY */
/* ============================================ */

// Copy extractor script to clipboard
const copyScriptBtn = document.getElementById('copyScriptBtn');
const extractorScript = document.getElementById('extractorScript');

if (copyScriptBtn && extractorScript) {
    copyScriptBtn.addEventListener('click', async () => {
        const scriptText = extractorScript.textContent;

        try {
            await navigator.clipboard.writeText(scriptText);

            // Change button to show success
            copyScriptBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            `;

            setTimeout(() => {
                copyScriptBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                `;
            }, 2000);
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    });
}

// Toggle visibility for Slack xoxc token
const toggleSlackXoxcBtn = document.getElementById('toggleSlackXoxcToken');
const slackXoxcInput = document.getElementById('slackXoxcToken');

if (toggleSlackXoxcBtn && slackXoxcInput) {
    toggleSlackXoxcBtn.addEventListener('click', () => {
        const type = slackXoxcInput.type === 'password' ? 'text' : 'password';
        slackXoxcInput.type = type;

        const svg = toggleSlackXoxcBtn.querySelector('svg');
        if (type === 'text') {
            svg.innerHTML = `
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
            `;
        } else {
            svg.innerHTML = `
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
            `;
        }
    });
}

// Toggle visibility for Slack xoxd token
const toggleSlackXoxdBtn = document.getElementById('toggleSlackXoxdToken');
const slackXoxdInput = document.getElementById('slackXoxdToken');

if (toggleSlackXoxdBtn && slackXoxdInput) {
    toggleSlackXoxdBtn.addEventListener('click', () => {
        const type = slackXoxdInput.type === 'password' ? 'text' : 'password';
        slackXoxdInput.type = type;

        const svg = toggleSlackXoxdBtn.querySelector('svg');
        if (type === 'text') {
            svg.innerHTML = `
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
            `;
        } else {
            svg.innerHTML = `
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
            `;
        }
    });
}

// Save Slack tokens
const saveSlackTokenBtn = document.getElementById('saveSlackTokenBtn');
const slackStatusMessage = document.getElementById('slackStatusMessage');

if (saveSlackTokenBtn && slackXoxcInput && slackXoxdInput && slackStatusMessage) {
    saveSlackTokenBtn.addEventListener('click', async () => {
        const xoxcToken = slackXoxcInput.value.trim();
        const xoxdToken = slackXoxdInput.value.trim();

        if (!xoxcToken || !xoxdToken) {
            showSlackStatus('error', 'Please enter both xoxc and xoxd tokens');
            return;
        }

        if (!xoxcToken.startsWith('xoxc-')) {
            showSlackStatus('error', 'Invalid xoxc token format. Token should start with "xoxc-"');
            return;
        }

        if (!xoxdToken.startsWith('xoxd-')) {
            showSlackStatus('error', 'Invalid xoxd token format. Token should start with "xoxd-"');
            return;
        }

        // Show loading state
        saveSlackTokenBtn.disabled = true;
        saveSlackTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Saving...
        `;

        try {
            const response = await fetch('/api/settings/slack-tokens', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ xoxc: xoxcToken, xoxd: xoxdToken })
            });

            const data = await response.json();

            if (response.ok) {
                showSlackStatus('success', data.message || 'Slack tokens saved successfully!');
            } else {
                showSlackStatus('error', data.message || 'Failed to save Slack tokens');
            }
        } catch (error) {
            showSlackStatus('error', 'An error occurred while saving the tokens');
        } finally {
            // Restore button
            saveSlackTokenBtn.disabled = false;
            saveSlackTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/>
                    <polyline points="7 3 7 8 15 8"/>
                </svg>
                Save Tokens
            `;
        }
    });
}

// Test Slack tokens
const testSlackTokenBtn = document.getElementById('testSlackTokenBtn');

if (testSlackTokenBtn && slackXoxcInput && slackXoxdInput && slackStatusMessage) {
    testSlackTokenBtn.addEventListener('click', async () => {
        const xoxcToken = slackXoxcInput.value.trim();
        const xoxdToken = slackXoxdInput.value.trim();

        if (!xoxcToken || !xoxdToken) {
            showSlackStatus('error', 'Please enter both xoxc and xoxd tokens to test');
            return;
        }

        // Show loading state
        testSlackTokenBtn.disabled = true;
        testSlackTokenBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
            Testing...
        `;

        try {
            const response = await fetch('/api/settings/test-slack-tokens', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({ xoxc: xoxcToken, xoxd: xoxdToken })
            });

            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch (e) {
                showSlackStatus('error', `❌ Server error (${response.status}): ${text.substring(0, 200) || 'Empty response'}`);
                return;
            }

            if (response.ok) {
                showSlackStatus('success', data.message || 'Connection successful! Tokens are valid.');
            } else {
                showSlackStatus('error', data.message || 'Connection failed. Please check your tokens.');
            }
        } catch (error) {
            showSlackStatus('error', `❌ Error: ${error.message}`);
        } finally {
            // Restore button
            testSlackTokenBtn.disabled = false;
            testSlackTokenBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                Test Connection
            `;
        }
    });
}

// Helper function to show Slack status messages
function showSlackStatus(type, message) {
    if (!slackStatusMessage) return;

    slackStatusMessage.className = 'status-message show ' + type;
    slackStatusMessage.textContent = message;

    // Auto-hide after 5 seconds
    setTimeout(() => {
        slackStatusMessage.classList.remove('show');
    }, 5000);
}

// Load saved Slack tokens on page load
async function loadSavedSlackTokens() {
    if (!slackXoxcInput || !slackXoxdInput) return;

    try {
        const response = await fetch('/api/settings/slack-tokens');
        if (response.ok) {
            const data = await response.json();
            if (data.xoxc) {
                slackXoxcInput.value = data.xoxc;
            }
            if (data.xoxd) {
                slackXoxdInput.value = data.xoxd;
            }
        }
    } catch (error) {
        console.error('Error loading saved Slack tokens:', error);
    }
}

// Initialize Slack token section
if (slackXoxcInput && slackXoxdInput) {
    loadSavedSlackTokens();
}

// Source filter functionality
const selectAllSourcesCheckbox = document.querySelector('.select-all-sources');
const sourceFilterCheckboxes = document.querySelectorAll('.source-filter');

// Function to update result sections visibility
function updateResultsVisibility() {
    sourceFilterCheckboxes.forEach(checkbox => {
        const source = checkbox.getAttribute('data-source');
        const resultSection = document.querySelector(`.results-section[data-source="${source}"]`);

        if (resultSection) {
            if (checkbox.checked) {
                resultSection.style.display = 'block';
            } else {
                resultSection.style.display = 'none';
            }
        }
    });

    // Update global results UI visibility
    updateSearchResultsDisplay();
}

// Function to show/hide results header and pagination based on whether results exist
function updateSearchResultsDisplay() {
    const resultsHeader = document.querySelector('.results-header');
    const pagination = document.querySelector('.pagination');
    const allResultSections = document.querySelectorAll('.results-section');

    // Check if any result section has content
    let hasResults = false;
    allResultSections.forEach(section => {
        const content = section.querySelector('.section-content');
        const hasContent = content && content.children.length > 0;

        if (hasContent) {
            hasResults = true;
        }
    });

    // Show/hide results header and pagination
    if (resultsHeader) {
        resultsHeader.style.display = hasResults ? 'flex' : 'none';
    }
    if (pagination) {
        pagination.style.display = hasResults ? 'flex' : 'none';
    }
}

// Select All functionality
if (selectAllSourcesCheckbox) {
    selectAllSourcesCheckbox.addEventListener('change', function() {
        sourceFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = this.checked;
        });
        updateResultsVisibility();
    });
}

// Individual source checkbox functionality
sourceFilterCheckboxes.forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        // Close Details panel when filters change
        const detailPanelEl = document.querySelector('.detail-panel');
        if (detailPanelEl && detailPanelEl.classList.contains('visible')) {
            detailPanelEl.classList.remove('visible');
            detailPanelEl.classList.remove('expanded');
            console.log('🔄 Closed Details panel due to filter change');
        }

        // Update Select All checkbox state
        const allChecked = Array.from(sourceFilterCheckboxes).every(cb => cb.checked);
        const noneChecked = Array.from(sourceFilterCheckboxes).every(cb => !cb.checked);

        if (selectAllSourcesCheckbox) {
            selectAllSourcesCheckbox.checked = allChecked;
            selectAllSourcesCheckbox.indeterminate = !allChecked && !noneChecked;
        }

        updateResultsVisibility();
    });
});

// Product filter functionality
const selectAllProductsCheckbox = document.querySelector('.select-all-products');
const productFilterCheckboxes = document.querySelectorAll('.product-filter');

// Function to filter results by product
// Helper function to detect products mentioned in search query
function detectProductsInQuery(query) {
    if (!query) return [];

    const queryLower = query.toLowerCase();
    const detectedProducts = [];

    // Check for each product keyword in the query
    // Order matters: check specific terms before generic ones

    if (queryLower.includes('rosa hcp') || queryLower.includes('rosa-hcp')) {
        detectedProducts.push('rosa-hcp');
    }
    if (queryLower.includes('aro hcp') || queryLower.includes('aro-hcp')) {
        detectedProducts.push('aro-hcp');
    }
    if (queryLower.includes('rosa') && !detectedProducts.includes('rosa-hcp')) {
        // If query contains "rosa" but not already added rosa-hcp
        // Add both ROSA and ROSA HCP (user searching "rosa" likely wants both)
        detectedProducts.push('rosa', 'rosa-hcp');
    }
    if (queryLower.includes('aro') && !detectedProducts.includes('aro-hcp')) {
        // Add both ARO and ARO HCP
        detectedProducts.push('aro', 'aro-hcp');
    }
    if (queryLower.includes('osd') || queryLower.includes('openshift dedicated')) {
        detectedProducts.push('osd');
    }

    console.log(`🔍 Detected products in query "${query}":`, detectedProducts);
    return detectedProducts;
}

// Helper function to auto-select products in filter based on search query
function autoSelectProductsFromQuery(query) {
    const detectedProducts = detectProductsInQuery(query);

    if (detectedProducts.length > 0) {
        console.log(`✅ Auto-selecting products:`, detectedProducts);

        // Uncheck all products first
        productFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });

        // Check only detected products
        detectedProducts.forEach(product => {
            const checkbox = document.querySelector(`.product-filter[data-product="${product}"]`);
            if (checkbox) {
                checkbox.checked = true;
                console.log(`  ✓ Checked: ${product}`);
            }
        });

        // Update Select All checkbox state
        const allChecked = Array.from(productFilterCheckboxes).every(cb => cb.checked);
        const noneChecked = Array.from(productFilterCheckboxes).every(cb => !cb.checked);

        if (selectAllProductsCheckbox) {
            selectAllProductsCheckbox.checked = allChecked;
            selectAllProductsCheckbox.indeterminate = !allChecked && !noneChecked;
        }

        // Apply the filtering
        filterResultsByProduct();
    } else {
        console.log('ℹ️ No products detected in query, showing all products');
        productFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = true;
        });
        if (selectAllProductsCheckbox) {
            selectAllProductsCheckbox.checked = true;
            selectAllProductsCheckbox.indeterminate = false;
        }
        filterResultsByProduct();
    }
}

// Helper function to extract and normalize product name
// Copy KCS Article Link to clipboard
function copyKCSLink(button) {
    const url = button.getAttribute('data-url');
    if (!url) {
        alert('No URL available to copy');
        return;
    }

    // Use modern clipboard API
    navigator.clipboard.writeText(url).then(() => {
        // Show success feedback
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.style.background = '#4caf50';
        button.style.color = '#fff';
        button.style.borderColor = '#4caf50';

        // Reset after 2 seconds
        setTimeout(() => {
            button.textContent = originalText;
            button.style.background = '#fff';
            button.style.color = '#333';
            button.style.borderColor = '#e0e0e0';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = url;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            button.textContent = '✓ Copied!';
            button.style.background = '#4caf50';
            button.style.color = '#fff';
            setTimeout(() => {
                button.textContent = 'Copy KCS Article Link';
                button.style.background = '#fff';
                button.style.color = '#333';
            }, 2000);
        } catch (err) {
            alert('Failed to copy link');
        }
        document.body.removeChild(textArea);
    });
}

function copyGitHubLink(button) {
    const url = button.getAttribute('data-url');
    if (!url) {
        alert('No URL available to copy');
        return;
    }

    // Use modern clipboard API
    navigator.clipboard.writeText(url).then(() => {
        // Show success feedback
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.style.background = '#4caf50';
        button.style.color = '#fff';
        button.style.borderColor = '#4caf50';

        // Reset after 2 seconds
        setTimeout(() => {
            button.textContent = originalText;
            button.style.background = '#fff';
            button.style.color = '#333';
            button.style.borderColor = '#e0e0e0';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy GitHub link');
    });
}

function copyGitLabLink(button) {
    const url = button.getAttribute('data-url');
    if (!url) {
        alert('No URL available to copy');
        return;
    }

    // Use modern clipboard API
    navigator.clipboard.writeText(url).then(() => {
        // Show success feedback
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.style.background = '#4caf50';
        button.style.color = '#fff';
        button.style.borderColor = '#4caf50';

        // Reset after 2 seconds
        setTimeout(() => {
            button.textContent = originalText;
            button.style.background = '#fff';
            button.style.color = '#333';
            button.style.borderColor = '#e0e0e0';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy GitLab link');
    });
}

async function fetchFileDescription(resultData, source) {
    const descriptionElement = document.querySelector('.description-content');
    if (!descriptionElement) return;

    if (resultData.ask_sre && resultData.summary) {
        descriptionElement.textContent = resultData.summary;
        descriptionElement.style.color = '#333';
        return;
    }

    try {
        const isGitHub = source === 'github';
        const endpoint = isGitHub ? '/api/github-file-content' : '/api/gitlab-file-content';

        let payload = {};
        if (isGitHub) {
            payload = {
                repository: resultData.repository,
                path: resultData.path,
                sha: resultData.sha || ''
            };
        } else {
            payload = {
                project_id: resultData.project_id,
                project_name: resultData.project_name,
                path: resultData.path,
                ref: resultData.ref || 'main'
            };
        }

        console.log(`🔍 Fetching ${isGitHub ? 'GitHub' : 'GitLab'} file content:`, payload);

        // The endpoint uses session tokens from the backend, so no need to pass config
        // The backend proxy (seekrWebUI_server.py) will forward the request with session tokens
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',  // Include session cookies to get tokens from backend session
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        console.log(`📄 File content response:`, data);

        if (data.success) {
            descriptionElement.textContent = data.content;
            descriptionElement.style.color = '#333';

            // Show repository info message
            const infoText = document.createElement('p');
            infoText.style.cssText = 'color: #666; font-style: italic; margin-top: 1rem; font-size: 0.875rem;';
            infoText.textContent = 'View full repository for complete details';
            descriptionElement.parentNode.appendChild(infoText);
        } else {
            descriptionElement.innerHTML = `<em style="color: #999;">Unable to load file preview: ${data.error}</em>`;
        }
    } catch (error) {
        console.error('❌ Error fetching file description:', error);
        descriptionElement.innerHTML = `<em style="color: #999;">Unable to load file preview: ${error.message}</em>`;
    }
}

function extractProductTag(productString) {
    if (!productString) return null;

    // Handle array of products (some APIs return arrays)
    let productText = productString;
    if (Array.isArray(productString)) {
        // Join array items or take first item
        productText = productString.join(' ');
    }

    const productLower = productText.toLowerCase();

    // Match exact product names (order matters - check longer/specific names first)

    // ROSA HCP: "Red Hat OpenShift Service on AWS Hosted Control Planes"
    if (productLower.includes('openshift service on aws') && productLower.includes('hosted control plane')) {
        return 'rosa-hcp';
    }

    // ARO HCP: "Azure Red Hat OpenShift Hosted Control Planes"
    if (productLower.includes('azure') && productLower.includes('hosted control plane')) {
        return 'aro-hcp';
    }

    // ROSA: "Red Hat OpenShift Service on AWS" or "Red Hat OpenShift on AWS"
    if ((productLower.includes('openshift service on aws') || productLower.includes('openshift on aws')) && !productLower.includes('hosted control plane')) {
        return 'rosa';
    }

    // ARO: "Azure Red Hat OpenShift"
    if (productLower.includes('azure red hat openshift') && !productLower.includes('hosted control plane')) {
        return 'aro';
    }

    // OSD: "OpenShift Dedicated"
    if (productLower.includes('openshift dedicated')) {
        return 'osd';
    }

    return null;  // No matching product
}

// Update product filter counts based on current results
function updateProductCounts() {
    console.log('📊 updateProductCounts called');
    const productCounts = {
        'aro': 0,
        'aro-hcp': 0,
        'osd': 0,
        'rosa': 0,
        'rosa-hcp': 0
    };

    // Count all visible result items by product
    const itemsWithProduct = document.querySelectorAll('.result-item[data-product]');
    console.log(`🔍 Found ${itemsWithProduct.length} items with data-product attribute`);

    itemsWithProduct.forEach(item => {
        const product = item.getAttribute('data-product');
        console.log(`  - Item has product: ${product}`);
        if (productCounts.hasOwnProperty(product)) {
            productCounts[product]++;
        }
    });

    console.log('📊 Product counts:', productCounts);

    // Update filter counts in UI
    Object.keys(productCounts).forEach(product => {
        const checkbox = document.querySelector(`.product-filter[data-product="${product}"]`);
        if (checkbox) {
            const countSpan = checkbox.parentElement.querySelector('.filter-count');
            if (countSpan) {
                countSpan.textContent = `(${productCounts[product]})`;
            }
        }
    });

    // Update "Select All" count
    const totalCount = Object.values(productCounts).reduce((sum, count) => sum + count, 0);
    const selectAllCheckbox = document.querySelector('.select-all-products');
    if (selectAllCheckbox) {
        const countSpan = selectAllCheckbox.parentElement.querySelector('.filter-count');
        if (countSpan) {
            countSpan.textContent = `(${totalCount})`;
        }
    }
}

function filterResultsByProduct() {
    const checkedProducts = Array.from(productFilterCheckboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.getAttribute('data-product'));

    // When ALL products are checked, treat as "no filter" — show everything
    const allChecked = checkedProducts.length === productFilterCheckboxes.length;
    window.activeProductFilters = allChecked ? new Set() : new Set(checkedProducts);

    // Reset pagination to page 1 for all sources when filter changes
    if (window.paginationState) {
        Object.keys(window.paginationState).forEach(source => {
            window.paginationState[source].currentPage = 1;
        });
    }

    // Re-render SFDC results with new filters and pagination
    if (window.lastSearchResults && window.lastSearchResults.sfdc && window.paginationState) {
        renderSFDCResults(window.lastSearchResults.sfdc);
    }

    // Keep the old CSS-based filtering for non-SFDC sources (for now)
    const allResultSections = document.querySelectorAll('.results-section[data-source]');

    allResultSections.forEach(section => {
        const sourceType = section.getAttribute('data-source');

        // Skip SFDC since it's now re-rendered with pagination
        if (sourceType === 'salesforce') return;

        // Only apply product filtering to sections that are visible due to source filtering
        if (section.style.display !== 'none') {
            const resultItems = section.querySelectorAll('.result-item');

            resultItems.forEach(item => {
                const itemProduct = item.getAttribute('data-product');

                if (checkedProducts.length === 0 || allChecked) {
                    item.style.display = 'block';
                }
                else if (itemProduct) {
                    item.style.display = checkedProducts.includes(itemProduct) ? 'block' : 'none';
                }
                else {
                    item.style.display = 'block';
                }
            });
        }
    });
}

// Select All Products functionality
if (selectAllProductsCheckbox) {
    selectAllProductsCheckbox.addEventListener('change', function() {
        productFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = this.checked;
        });
        filterResultsByProduct();
    });
}

// Individual product checkbox functionality
productFilterCheckboxes.forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        // Update Select All checkbox state
        const allChecked = Array.from(productFilterCheckboxes).every(cb => cb.checked);
        const noneChecked = Array.from(productFilterCheckboxes).every(cb => !cb.checked);

        if (selectAllProductsCheckbox) {
            selectAllProductsCheckbox.checked = allChecked;
            selectAllProductsCheckbox.indeterminate = !allChecked && !noneChecked;
        }

        filterResultsByProduct();
    });
});

// Clear Sources button
const clearSourcesBtn = document.querySelector('.clear-sources-btn');
if (clearSourcesBtn) {
    clearSourcesBtn.addEventListener('click', () => {
        // Uncheck Select All checkbox and clear indeterminate state
        if (selectAllSourcesCheckbox) {
            selectAllSourcesCheckbox.checked = false;
            selectAllSourcesCheckbox.indeterminate = false;
        }
        // Uncheck all individual source checkboxes
        sourceFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });
        // Update results visibility
        updateResultsVisibility();
    });
}

// Clear Products button
const clearProductsBtn = document.querySelector('.clear-products-btn');
if (clearProductsBtn) {
    clearProductsBtn.addEventListener('click', () => {
        // Uncheck Select All checkbox and clear indeterminate state
        if (selectAllProductsCheckbox) {
            selectAllProductsCheckbox.checked = false;
            selectAllProductsCheckbox.indeterminate = false;
        }
        // Uncheck all individual product checkboxes
        productFilterCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });
        // Update product filtering
        filterResultsByProduct();
    });
}

// Toggle sections (Salesforce, OHSS, Slack, etc.)
document.querySelectorAll('.expand-section-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        btn.closest('.results-section').classList.toggle('collapsed');
    });
});

// Select result items
document.querySelectorAll('.result-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.result-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
    });
});

// Tab switching - Detail tabs
document.querySelectorAll('.detail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Lazy load external trackers when OHSS tab is clicked
        if (tab.dataset.tab === 'escalation-ohss') {
            const trackersElement = document.getElementById('detail-external-trackers');
            if (trackersElement && trackersElement.dataset.loaded === 'false') {
                const caseNumber = trackersElement.dataset.caseNumber;
                if (caseNumber) {
                    console.log('🔄 Lazy loading external trackers for case:', caseNumber);
                    trackersElement.innerHTML = '<p style="color: #666;">Loading external trackers...</p>';
                    trackersElement.dataset.loaded = 'loading';

                    fetch(`/api/case-escalations/${caseNumber}`, {
                        credentials: 'include'
                    })
                        .then(response => {
                            if (!response.ok) throw new Error(`HTTP ${response.status}`);
                            return response.json();
                        })
                        .then(data => {
                            console.log('📋 Tracker data received:', data);

                            const rawTrackers = data.external_trackers || [];

                            if (rawTrackers && Array.isArray(rawTrackers) && rawTrackers.length > 0) {
                                // Format: <OHSS ticketNumber> [OHSS link] - <OHSS ticketTitle> - (<OHSS_status>)
                                const trackersList = rawTrackers.map(tracker => {
                                    const ticketNumber = tracker.resourceKey || 'N/A';
                                    const ticketURL = tracker.resourceURL || '#';
                                    const ticketTitle = tracker.title || 'No description';
                                    const ticketStatus = tracker.status || 'Unknown';

                                    return `<div style="margin-bottom: 8px;"><a href="${ticketURL}" target="_blank" style="color: #0052CC; text-decoration: none;">${ticketNumber}</a> - ${ticketTitle} - (${ticketStatus})</div>`;
                                }).join('');

                                trackersElement.innerHTML = trackersList;
                            } else {
                                trackersElement.innerHTML = '<p style="color: #666;">No external trackers found</p>';
                            }

                            trackersElement.dataset.loaded = 'true';
                        })
                        .catch(error => {
                            console.error('Error loading external trackers:', error);
                            trackersElement.innerHTML = '<p style="color: #999;">Failed to load external trackers</p>';
                            trackersElement.dataset.loaded = 'error';
                        });
                }
            }
        }
    });
});

// Tab switching - Related tabs
document.querySelectorAll('.related-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
    });
});

// Filter section collapse (Sources, Products, etc.)
document.querySelectorAll('.filter-section-header').forEach(header => {
    header.addEventListener('click', () => {
        const filterSection = header.closest('.filter-section');
        filterSection.classList.toggle('collapsed');

        // Update tooltip text based on state
        const sectionTitle = header.querySelector('.filter-section-title').textContent;
        if (filterSection.classList.contains('collapsed')) {
            header.setAttribute('title', `Expand ${sectionTitle}`);
        } else {
            header.setAttribute('title', `Collapse ${sectionTitle}`);
        }
    });
});

// Filters panel collapse toggle
const collapseBtn = document.querySelector('.collapse-btn');
const filtersPanel = document.querySelector('.filters-panel');

if (collapseBtn && filtersPanel) {
    collapseBtn.addEventListener('click', () => {
        filtersPanel.classList.toggle('collapsed');

        // Update tooltip text based on state
        if (filtersPanel.classList.contains('collapsed')) {
            collapseBtn.setAttribute('title', 'Show Filters');
        } else {
            collapseBtn.setAttribute('title', 'Hide Filters');
        }
    });
}

// Detail panel expand/collapse toggle
const expandPanelBtn = document.querySelector('.expand-panel-btn');
const detailPanel = document.querySelector('.detail-panel');

if (expandPanelBtn && detailPanel) {
    const expandIcon = expandPanelBtn.querySelector('.expand-icon-img');
    const collapseIcon = expandPanelBtn.querySelector('.collapse-icon-img');

    expandPanelBtn.addEventListener('click', () => {
        detailPanel.classList.toggle('expanded');

        // Toggle icons and tooltip
        if (detailPanel.classList.contains('expanded')) {
            expandIcon.style.display = 'none';
            collapseIcon.style.display = 'block';
            expandPanelBtn.setAttribute('title', 'Collapse');
        } else {
            expandIcon.style.display = 'block';
            collapseIcon.style.display = 'none';
            expandPanelBtn.setAttribute('title', 'Expand');
        }
    });
}

// Close detail panel button
const closeDetailBtn = document.querySelector('.close-detail-btn');
if (closeDetailBtn && detailPanel) {
    closeDetailBtn.addEventListener('click', () => {
        detailPanel.classList.remove('visible');
        detailPanel.classList.remove('expanded');

        // Reset expand button state
        if (expandPanelBtn) {
            const expandIcon = expandPanelBtn.querySelector('.expand-icon-img');
            const collapseIcon = expandPanelBtn.querySelector('.collapse-icon-img');
            if (expandIcon && collapseIcon) {
                expandIcon.style.display = 'block';
                collapseIcon.style.display = 'none';
                expandPanelBtn.setAttribute('title', 'Expand');
            }
        }

        // Expand the Filters panel when Details panel is closed
        const filtersPanel = document.querySelector('.filters-panel');
        if (filtersPanel && filtersPanel.classList.contains('collapsed')) {
            filtersPanel.classList.remove('collapsed');
            filtersPanel.classList.add('expanded');
            console.log('✅ Expanded filters panel');
        }
    });
}

/* ============================================ */
/* METHOD TAB SWITCHING */
/* ============================================ */

const methodTabs = document.querySelectorAll('.method-tab');
const methodContents = document.querySelectorAll('.method-content');

if (methodTabs.length > 0 && methodContents.length > 0) {
    methodTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active class from all tabs and contents
            methodTabs.forEach(t => t.classList.remove('active'));
            methodContents.forEach(c => c.classList.remove('active'));

            // Add active class to clicked tab
            tab.classList.add('active');

            // Show corresponding content
            const method = tab.getAttribute('data-method');
            const content = document.getElementById(method + '-method');
            if (content) {
                content.classList.add('active');
            }
        });
    });
}

/* ============================================ */
/* TOKEN EXPIRY TRACKING AND NOTIFICATIONS */
/* ============================================ */

// Check token status on page load
async function checkTokenStatus() {
    try {
        const response = await fetch('/api/settings/token-status');
        if (response.ok) {
            const status = await response.json();

            // Update UI with expiry information
            updateTokenExpiryUI('atlassian', status.atlassian);
            updateTokenExpiryUI('redhat', status.redhat);
            updateTokenExpiryUI('slack', status.slack);

            // Show warnings for tokens expiring soon or expired
            // Check for revoked token first (highest priority)
            if (status.atlassian.revoked) {
                showRevokedNotification('atlassian', status.atlassian.revoked_reason || 'Token has been revoked');
            } else if (status.atlassian.configured && status.atlassian.days_remaining !== null) {
                if (status.atlassian.expired) {
                    showExpiryWarning('atlassian', 'expired');
                } else if (status.atlassian.days_remaining <= 7) {
                    showExpiryWarning('atlassian', 'expiring', status.atlassian.days_remaining);
                }
            }

            if (status.redhat.configured && status.redhat.days_remaining !== null) {
                if (status.redhat.expired) {
                    showExpiryWarning('redhat', 'expired');
                } else if (status.redhat.days_remaining <= 7) {
                    showExpiryWarning('redhat', 'expiring', status.redhat.days_remaining);
                }
            }
        }
    } catch (error) {
        console.error('Error checking token status:', error);
    }
}

// Update UI to show expiry information
function updateTokenExpiryUI(tokenType, statusData) {
    if (!statusData.configured) return;

    const expiryInfoId = `${tokenType}ExpiryInfo`;
    let expiryInfoElement = document.getElementById(expiryInfoId);

    // Create expiry info element if it doesn't exist
    if (!expiryInfoElement) {
        const cardBody = document.querySelector(`#${tokenType}Token`)?.closest('.card-body');
        if (!cardBody) return;

        expiryInfoElement = document.createElement('div');
        expiryInfoElement.id = expiryInfoId;
        expiryInfoElement.className = 'token-expiry-info';

        // Insert before the form actions
        const formActions = cardBody.querySelector('.form-actions');
        if (formActions) {
            cardBody.insertBefore(expiryInfoElement, formActions);
        }
    }

    // Update expiry info content
    if (statusData.expired) {
        expiryInfoElement.className = 'token-expiry-info expired';
        expiryInfoElement.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span><strong>Token Expired</strong> - Please generate a new token</span>
        `;
    } else if (statusData.days_remaining !== null) {
        const urgency = statusData.days_remaining <= 7 ? 'warning' : 'valid';
        expiryInfoElement.className = `token-expiry-info ${urgency}`;

        const icon = urgency === 'warning' ? `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
        ` : `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
            </svg>
        `;

        const message = statusData.days_remaining === 0
            ? 'Token expires today'
            : statusData.days_remaining === 1
            ? 'Token expires in 1 day'
            : `Token expires in ${statusData.days_remaining} days`;

        expiryInfoElement.innerHTML = `
            ${icon}
            <span>${message} (${formatDateToMMDDYYYY(statusData.expiry_date)})</span>
        `;
    }
}

// Show expiry warning notification
function showExpiryWarning(tokenType, warningType, daysRemaining) {
    const tokenName = tokenType === 'atlassian' ? 'Atlassian API' : 'Red Hat API';
    let title = '';
    let message = '';
    let notificationType = 'warning';

    if (warningType === 'expired') {
        title = `${tokenName} Token Expired`;
        message = 'Your token has expired. Please generate a new token in Settings.';
        notificationType = 'error';
    } else if (warningType === 'expiring') {
        title = `${tokenName} Token Expiring Soon`;
        message = `Your token expires in ${daysRemaining} day${daysRemaining > 1 ? 's' : ''}. Consider generating a new one.`;
    }

    if (!message) return;

    // Add to notifications array
    const notifications = getNotifications();

    // Check if notification already exists
    const notificationKey = `${tokenType}_${warningType}`;
    const existingIndex = notifications.findIndex(n => n.key === notificationKey);

    const notification = {
        key: notificationKey,
        type: notificationType,
        icon: 'alert',
        title: title,
        message: message,
        time: warningType === 'expired' ? 'Expired' : `${daysRemaining} day${daysRemaining > 1 ? 's' : ''} left`,
        link: '/seekr/settings',
        dismissible: true,
        dismissType: notificationKey
    };

    if (existingIndex >= 0) {
        // Update existing notification
        notifications[existingIndex] = notification;
    } else {
        // Add new notification at the beginning
        notifications.unshift(notification);
    }

    saveNotifications(notifications);

    // Update notification badge count
    updateNotificationBadge(notifications.length);

    // Re-render notifications if dropdown is open
    if (notificationDropdown && !notificationDropdown.classList.contains('hidden')) {
        renderNotifications(notifications);
    }

    console.log(`🔔 ${tokenName} ${warningType} - notification added`);
}

// Show revoked token notification (called by background validation)
function showRevokedNotification(tokenType, reason) {
    const tokenName = tokenType === 'atlassian' ? 'Atlassian API' : 'Red Hat API';

    // Add to notifications array
    const notifications = getNotifications();

    // Check if notification already exists
    const existingIndex = notifications.findIndex(n => n.key === `${tokenType}_revoked`);

    const notification = {
        key: `${tokenType}_revoked`,
        type: 'error',
        icon: 'alert',
        title: `${tokenName} Token Revoked`,
        message: reason || 'Your token has been revoked or is invalid. Please update it in Settings.',
        time: 'Just now',
        link: '/seekr/settings',
        dismissible: true,
        dismissType: `${tokenType}_revoked`
    };

    if (existingIndex >= 0) {
        // Update existing notification
        notifications[existingIndex] = notification;
    } else {
        // Add new notification at the beginning
        notifications.unshift(notification);
    }

    saveNotifications(notifications);

    // Update notification badge count
    updateNotificationBadge(notifications.length);

    // Re-render notifications if dropdown is open
    if (notificationDropdown && !notificationDropdown.classList.contains('hidden')) {
        renderNotifications(notifications);
    }

    console.log(`🔔 ${tokenName} token revoked - notification added`);
}

// Enhanced load saved token with expiry info
async function loadSavedTokenWithExpiry() {
    if (!atlassianTokenInput) return;

    try {
        const response = await fetch('/api/settings/atlassian-token');
        if (response.ok) {
            const data = await response.json();

            // Always populate email (auto-generated from Kerberos username)
            if (data.email && atlassianEmailInput) {
                atlassianEmailInput.value = data.email;
            }

            if (data.expired) {
                // Token expired, show message
                showStatus('error', data.message || 'Token has expired. Please generate a new one.');
                atlassianTokenInput.value = '';
            } else if (data.token) {
                atlassianTokenInput.value = data.token;

                // Show expiry info if available
                if (data.days_remaining !== undefined) {
                    updateTokenExpiryUI('atlassian', {
                        configured: true,
                        expired: false,
                        days_remaining: data.days_remaining,
                        expiry_date: data.expiry_date
                    });
                }
            }
        }
    } catch (error) {
        console.error('Error loading saved token:', error);
    }
}

// Enhanced load Red Hat token with expiry info
async function loadSavedRedhatTokenWithExpiry() {
    if (!redhatTokenInput) return;

    try {
        const response = await fetch('/api/settings/redhat-token');
        if (response.ok) {
            const data = await response.json();

            if (data.expired) {
                // Token expired, show message
                showRedhatStatus('error', data.message || 'Token has expired. Please generate a new one.');
                redhatTokenInput.value = '';
            } else if (data.token) {
                redhatTokenInput.value = data.token;

                // Show expiry info if available
                if (data.days_remaining !== undefined) {
                    updateTokenExpiryUI('redhat', {
                        configured: true,
                        expired: false,
                        days_remaining: data.days_remaining,
                        expiry_date: data.expiry_date
                    });
                }
            }
        }
    } catch (error) {
        console.error('Error loading saved Red Hat token:', error);
    }
}

// Initialize token expiry tracking on settings page
if (window.location.pathname === '/seekr/settings') {
    // Check token status when page loads
    checkTokenStatus();

    // Replace original load functions with expiry-aware versions
    if (atlassianTokenInput) {
        loadSavedTokenWithExpiry();
    }

    if (redhatTokenInput) {
        loadSavedRedhatTokenWithExpiry();
    }

    // Check token status periodically (every 5 minutes)
    setInterval(checkTokenStatus, 5 * 60 * 1000);
}

/* ============================================ */
/* SEARCH FUNCTIONALITY */
/* ============================================ */

// Version marker to verify code is loading
console.log('🚀 SeekrAI JavaScript Version: 14.2 - SYNTAX FIX - Loaded at ' + new Date().toISOString());

// Search button handler
document.addEventListener('DOMContentLoaded', async () => {
    const searchButton = document.querySelector('.search-button');
    const searchInput = document.querySelector('.search-input');

    if (searchButton && searchInput) {
        console.log('🔍 Search event listeners being attached');

        // Handle search button click
        searchButton.addEventListener('click', async (e) => {
            e.preventDefault();
            console.log('🔘 Search button clicked');
            await performSearch();
        });

        // Handle Enter key in search input
        searchInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                console.log('⏎ Enter key pressed in search input');
                await performSearch();
            }
        });

        console.log('✅ Search event listeners attached successfully');
    } else {
        console.warn('⚠️ Search button or input not found:', {searchButton, searchInput});
    }

    // Sort dropdown event listener
    const sortSelect = document.querySelector('.sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            window.currentSortBy = sortSelect.value;
            console.log(`🔀 Sort changed to: ${sortSelect.value}`);
            applySortToResults();
        });
    }

    // Handle section expand/collapse - click on header or button
    document.querySelectorAll('.section-header').forEach(header => {
        header.addEventListener('click', (e) => {
            const section = header.closest('.results-section');
            if (section) {
                section.classList.toggle('collapsed');
                console.log(`📂 Toggled section: ${section.dataset.source}, collapsed=${section.classList.contains('collapsed')}`);
            }
        });
    });

    // Initialize detail tabs
    initDetailTabs();

    // Check if there's a search query in the URL (from Settings page redirect)
    const urlParams = new URLSearchParams(window.location.search);
    const searchQuery = urlParams.get('q');

    if (searchQuery && searchInput) {
        // Fill the search input
        searchInput.value = searchQuery;

        // Trigger search automatically
        await performSearch();

        // Clean the URL (remove query parameter)
        window.history.replaceState({}, '', '/seekr/main');
    }

    // Check for pending search from Recent Searches page (at the end, after all setup)
    const pendingSearch = sessionStorage.getItem('pendingSearch');
    // Initialize Slack channel checkboxes
    initSlackChannels();

    if (pendingSearch) {
        console.log('📌 Found pending search in sessionStorage:', pendingSearch);
        sessionStorage.removeItem('pendingSearch');
        if (searchInput) {
            searchInput.value = pendingSearch;
            console.log('✅ Set search input value to:', pendingSearch);
            // Trigger search automatically
            setTimeout(async () => {
                console.log('🔍 Auto-executing search from recent history...');
                await performSearch();
            }, 300);
        } else {
            console.error('❌ Search input element not found!');
        }
    }
});

// ============================================================================
// Slack Channel Filter Functions
// ============================================================================

const COMMON_SLACK_CHANNELS = [
    'forum-rosa-support',
    'openshift-sre',
    'team-sre',
    'sre-alerts',
    'sre-general',
    'rosa-sre',
    'osd-sre',
    'forum-managed-openshift',
    'ask-sre',
];

let _slackChannelsInitialized = false;

async function initSlackChannels() {
    if (_slackChannelsInitialized) return;
    _slackChannelsInitialized = true;

    const container = document.getElementById('slack-channel-options');
    if (!container) return;

    let channels = COMMON_SLACK_CHANNELS;
    try {
        const resp = await fetch('/api/settings/slack-channels', {credentials: 'include'});
        if (resp.ok) {
            const data = await resp.json();
            if (Array.isArray(data.channels) && data.channels.length > 0) {
                channels = data.channels;
            }
        }
    } catch (e) { /* use defaults */ }

    channels.forEach(channel => {
        const label = document.createElement('label');
        label.className = 'filter-option channel-option';
        label.style.fontSize = '0.88em';
        label.innerHTML = `
            <input type="checkbox" class="filter-checkbox channel-filter" data-channel="${channel}" checked onchange="onChannelFilterChange()" />
            <span class="filter-label">#${channel}</span>
        `;
        container.appendChild(label);
    });
}

function getSelectedSlackChannels() {
    const allChannelsCheckbox = document.getElementById('channel-all');
    // "All Channels" checked → no restriction (null = search everything)
    if (!allChannelsCheckbox || allChannelsCheckbox.checked) return null;

    const channelCheckboxes = document.querySelectorAll('#slack-channel-options .channel-filter:checked');
    const channels = Array.from(channelCheckboxes).map(cb => cb.getAttribute('data-channel'));
    return channels;
}

function toggleAllSlackChannels(checkbox) {
    const channelCheckboxes = document.querySelectorAll('#slack-channel-options .channel-filter');
    channelCheckboxes.forEach(cb => { cb.checked = checkbox.checked; });
}

function clearSlackChannels() {
    const allChannelsCheckbox = document.getElementById('channel-all');
    if (allChannelsCheckbox) allChannelsCheckbox.checked = true;
    const channelCheckboxes = document.querySelectorAll('#slack-channel-options .channel-filter');
    channelCheckboxes.forEach(cb => { cb.checked = true; });
}

function onChannelFilterChange() {
    const channelCheckboxes = document.querySelectorAll('#slack-channel-options .channel-filter');
    const allChecked = Array.from(channelCheckboxes).every(cb => cb.checked);
    const allChannelsCheckbox = document.getElementById('channel-all');
    if (allChannelsCheckbox) allChannelsCheckbox.checked = allChecked;
}

// Add any channels found in search results that aren't already in the sidebar list
function syncSlackChannelsFromResults(messages) {
    const container = document.getElementById('slack-channel-options');
    if (!container || !messages || messages.length === 0) return;

    const existing = new Set(
        Array.from(container.querySelectorAll('.channel-filter')).map(cb => cb.getAttribute('data-channel'))
    );

    messages.forEach(msg => {
        const ch = msg.channel_name || msg.channel || '';
        if (!ch || ch.startsWith('C0') || existing.has(ch)) return; // skip raw IDs

        existing.add(ch);
        const label = document.createElement('label');
        label.className = 'filter-option channel-option';
        label.innerHTML = `
            <input type="checkbox" class="filter-checkbox channel-filter" data-channel="${ch}" checked onchange="onChannelFilterChange()" />
            <span class="filter-label">#${ch}</span>
        `;
        container.appendChild(label);
        onChannelFilterChange();
    });
}

async function performSearch() {
    const searchInput = document.querySelector('.search-input');
    const query = searchInput?.value?.trim();

    if (!query) {
        alert('Please enter a search query');
        return;
    }

    console.log('🔍 Performing search for:', query);

    // Close Details panel when starting a new search
    const detailPanelElement = document.querySelector('.detail-panel');
    if (detailPanelElement) {
        detailPanelElement.classList.remove('visible');
        detailPanelElement.classList.remove('expanded');
        console.log('🔄 Closed Details panel for new search');
    }

    // Close detail panel and clear old data
    const detailPanelElem = document.querySelector('.detail-panel');
    if (detailPanelElem) {
        detailPanelElem.classList.remove('open');
    }
    window.lastSearchResults = null;

    // Clear Related Content cache to force fresh fetches
    relatedContentCache.ohss = {};
    console.log('🧹 Cleared Related Content cache');

    // Update results header with query
    const resultsCount = document.querySelector('.results-count');
    if (resultsCount) {
        resultsCount.textContent = `Searching for "${query}"...`;
    }

    // Show loading state
    const searchButton = document.querySelector('.search-button');
    const originalText = searchButton.textContent;
    searchButton.textContent = 'Searching...';
    searchButton.disabled = true;

    // Show spinner, hide previous results
    const loadingEl = document.getElementById('search-loading');
    if (loadingEl) loadingEl.style.display = 'flex';
    document.querySelectorAll('.results-section').forEach(s => s.style.display = 'none');

    try {
        // Get currently selected sources
        const sourceCheckboxes = document.querySelectorAll('.source-filter');
        const selectedSources = Array.from(sourceCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.getAttribute('data-source'));

        console.log('🔍 Searching with selected sources:', selectedSources);

        // Call the search API via proxy (same origin, no CORS issues)
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',  // Include session cookies
            body: JSON.stringify({
                query: query,
                max_results: 20,
                sources: selectedSources,
                slack_channels: getSelectedSlackChannels()  // null = all channels
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const results = await response.json();
        console.log('✅ Search results:', results);

        // Display results (this will update the header with final count)
        displaySearchResults(results, query);

    } catch (error) {
        console.error('❌ Search error:', error);

        // Show user-friendly error message
        let errorMsg = 'Search failed. ';
        if (error.message.includes('Failed to fetch')) {
            errorMsg += 'Network error - check your connection.';
        } else {
            errorMsg += error.message;
        }

        alert(errorMsg + '\n\nCheck browser console (F12) for details.');
    } finally {
        // Reset button and hide spinner
        searchButton.textContent = originalText;
        searchButton.disabled = false;
        if (loadingEl) loadingEl.style.display = 'none';
    }
}

async function saveSearchToHistory(query, totalResults, results) {
    try {
        const sources = [];

        // Get currently selected/visible sources from the filter checkboxes
        const sourceCheckboxes = document.querySelectorAll('.source-filter');
        const selectedSources = Array.from(sourceCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.getAttribute('data-source'));

        // Only include sources that are BOTH selected AND have results
        selectedSources.forEach(source => {
            switch(source) {
                case 'salesforce':
                    if (results.sfdc?.cases?.length > 0) sources.push('sfdc');
                    break;
                case 'ohss':
                    if (results.jira?.issues?.length > 0) sources.push('jira');
                    break;
                case 'slack':
                    if (results.slack?.messages?.length > 0) sources.push('slack');
                    break;
                case 'kcs':
                    if (results.kcs?.articles?.length > 0 || results.kcs?.docs?.length > 0) sources.push('kcs');
                    break;
                case 'github':
                    if (results.github?.results?.length > 0) sources.push('github');
                    break;
                case 'gitlab':
                    if (results.gitlab?.results?.length > 0) sources.push('gitlab');
                    break;
            }
        });

        // Debug: Log what sources we're saving
        console.log('💾 Saving search to history:', {query, totalResults, sources, selectedSources});

        const response = await fetch('/api/search/save-history', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                query: query,
                results_count: totalResults,
                sources: sources
            })
        });

        if (response.ok) {
            console.log('✅ Search saved to history');
        }
    } catch (error) {
        console.error('Error saving search to history:', error);
        // Don't show error to user, this is background operation
    }
}

// Sort priority mappings (lower number = higher priority)
const PRIORITY_RANK = {
    'blocker': 1, 'critical': 2, 'major': 3, 'normal': 4, 'minor': 5, 'trivial': 6,
    'highest': 1, 'high': 2, 'medium': 3, 'low': 4, 'lowest': 5
};

const SEVERITY_RANK = {
    '1 (urgent)': 1, '1': 1, 'urgent': 1,
    '2 (high)': 2, '2': 2, 'high': 2,
    '3 (normal)': 3, '3': 3, 'normal': 3,
    '4 (low)': 4, '4': 4, 'low': 4
};

// Score a KCS article by product relevance to managed OpenShift (ROSA/ARO/HCP/OSD).
// 0 = priority product, 1 = generic/unknown, 2 = unrelated product
function getKCSProductScore(article) {
    const text = [
        article.title || '',
        article.documentTitle || '',
        article.product || '',
        article.summary || '',
    ].join(' ').toLowerCase();

    // Use word-boundary regex to avoid false matches (e.g. 'aro' inside 'workaround')
    const PRIORITY_PATTERNS = [
        /\brosa\b/, /\baro\b/, /\bhcp\b/, /hosted control plane/,
        /openshift service on aws/, /azure red hat openshift/,
        /openshift dedicated/, /\bosd\b/, /managed openshift/,
    ];
    const UNRELATED_PATTERNS = [
        /openstack/, /red hat satellite/, /satellite [67]/, /\bmicroshift\b/,
        /\bansible\b/, /enterprise linux/, /\brhel\b/, /\bvirtualization\b/,
        /\bceph\b/, /\brhosp\b/,
    ];

    if (PRIORITY_PATTERNS.some(p => p.test(text))) return 0;
    if (UNRELATED_PATTERNS.some(p => p.test(text))) return 2;
    return 1;
}

function applySortToResults() {
    const results = window.lastSearchResults;
    if (!results) return;

    const sortBy = window.currentSortBy || 'relevance';
    console.log(`🔀 Applying sort: ${sortBy}`);

    if (sortBy === 'date') {
        if (results.sfdc?.cases) {
            results.sfdc.cases.sort((a, b) => {
                const dateA = a.last_modified_date || a.created_date || '';
                const dateB = b.last_modified_date || b.created_date || '';
                return dateB.localeCompare(dateA);
            });
        }
        if (results.jira?.issues) {
            results.jira.issues.sort((a, b) => {
                const dateA = a.updated || a.created || '';
                const dateB = b.updated || b.created || '';
                return dateB.localeCompare(dateA);
            });
        }
        if (results.slack?.messages) {
            results.slack.messages.sort((a, b) => {
                const tsA = a.ts || a.thread_ts || '0';
                const tsB = b.ts || b.thread_ts || '0';
                return parseFloat(tsB) - parseFloat(tsA);
            });
        }
        if (results.kcs?.articles) {
            results.kcs.articles.sort((a, b) => {
                const dateA = a.modified_date || '';
                const dateB = b.modified_date || '';
                return dateB.localeCompare(dateA);
            });
        }
    } else if (sortBy === 'priority') {
        if (results.sfdc?.cases) {
            results.sfdc.cases.sort((a, b) => {
                const rankA = SEVERITY_RANK[(a.severity || '').toLowerCase()] || 99;
                const rankB = SEVERITY_RANK[(b.severity || '').toLowerCase()] || 99;
                return rankA - rankB;
            });
        }
        if (results.jira?.issues) {
            results.jira.issues.sort((a, b) => {
                const rankA = PRIORITY_RANK[(a.priority || '').toLowerCase()] || 99;
                const rankB = PRIORITY_RANK[(b.priority || '').toLowerCase()] || 99;
                return rankA - rankB;
            });
        }
    } else {
        // Relevance — restore original API order
        if (results.sfdc?.cases) results.sfdc.cases.sort((a, b) => a._originalIndex - b._originalIndex);
        if (results.jira?.issues) results.jira.issues.sort((a, b) => a._originalIndex - b._originalIndex);
        if (results.slack?.messages) results.slack.messages.sort((a, b) => a._originalIndex - b._originalIndex);
        if (results.github?.results) results.github.results.sort((a, b) => a._originalIndex - b._originalIndex);
        if (results.gitlab?.results) results.gitlab.results.sort((a, b) => a._originalIndex - b._originalIndex);

        // KCS: product-boosted relevance sort
        // Score 0 = ROSA/ARO/HCP/OSD (highest priority)
        // Score 1 = generic OpenShift / unknown
        // Score 2 = unrelated products (OpenStack, Satellite, RHEL, etc.)
        if (results.kcs?.articles) {
            results.kcs.articles.sort((a, b) => {
                const scoreA = getKCSProductScore(a);
                const scoreB = getKCSProductScore(b);
                if (scoreA !== scoreB) return scoreA - scoreB;
                return a._originalIndex - b._originalIndex; // stable: preserve API order within same group
            });
        }
    }

    // Reset pagination to page 1 after re-sort
    if (window.paginationState) {
        Object.keys(window.paginationState).forEach(key => {
            window.paginationState[key].currentPage = 1;
        });
    }

    // Re-render all sections with sorted data
    renderSFDCResults(results.sfdc || {cases: [], total: 0});
    renderJiraResults(results.jira || {issues: [], total: 0});
    renderSlackResults(results.slack || {messages: [], total: 0});
    syncSlackChannelsFromResults(results.slack?.messages);
    renderKCSResults(results.kcs || {articles: [], total: 0});
    renderGitHubResults(results.github || {results: [], total: 0});
    renderGitLabResults(results.gitlab || {results: [], total: 0});

    // Re-apply visibility and product filters
    updateResultsVisibility();
    updateProductCounts();
}

function displaySearchResults(results, query) {
    console.log('🎯 displaySearchResults called');
    console.log('📦 Full results object:', results);
    console.log('🔍 Query:', query);

    // CRITICAL: Clear old results first to prevent data contamination
    window.lastSearchResults = null;

    // Log each source's counts
    console.log('📊 SFDC:', results.sfdc?.cases?.length || 0, 'cases, total:', results.sfdc?.total || 0);
    if (results.sfdc?.cases && results.sfdc.cases.length > 0) {
        console.log('📋 SFDC Case Summaries:');
        results.sfdc.cases.forEach((c, i) => {
            console.log(`   ${i + 1}. [${c.case_number}] ${c.summary}`);
        });
    }
    console.log('📊 Jira:', results.jira?.issues?.length || 0, 'issues, total:', results.jira?.total || 0);
    console.log('📊 KCS:', results.kcs?.articles?.length || 0, 'articles, total:', results.kcs?.total || 0);
    // Calculate total results based on ACTUAL displayed items, not total matches
    const totalResults =
        (results.jira?.issues?.length || 0) +
        (results.sfdc?.cases?.length || 0) +
        (results.slack?.messages?.length || 0) +
        (results.kcs?.articles?.length || 0) +
        (results.github?.results?.length || 0) +
        (results.gitlab?.results?.length || 0);

    console.log(`📈 Total displayed results: ${totalResults}`);

    // Update results header with count and query
    const resultsCount = document.querySelector('.results-count');
    if (resultsCount && query) {
        resultsCount.textContent = `${totalResults} results for "${query}"`;
        console.log(`✅ Updated header: "${totalResults} results for ${query}"`);
    }

    // Save search to history
    saveSearchToHistory(query, totalResults, results);

    // Store results globally for detail panel
    window.lastSearchResults = results;

    // Tag each result with original index for Relevance sort restore
    if (results.sfdc?.cases) results.sfdc.cases.forEach((item, i) => item._originalIndex = i);
    if (results.jira?.issues) results.jira.issues.forEach((item, i) => item._originalIndex = i);
    if (results.slack?.messages) results.slack.messages.forEach((item, i) => item._originalIndex = i);
    if (results.kcs?.articles) results.kcs.articles.forEach((item, i) => item._originalIndex = i);
    if (results.github?.results) results.github.results.forEach((item, i) => item._originalIndex = i);
    if (results.gitlab?.results) results.gitlab.results.forEach((item, i) => item._originalIndex = i);

    // Apply product-boosted sort to KCS before first render
    if (results.kcs?.articles) {
        results.kcs.articles.sort((a, b) => {
            const scoreA = getKCSProductScore(a);
            const scoreB = getKCSProductScore(b);
            if (scoreA !== scoreB) return scoreA - scoreB;
            return a._originalIndex - b._originalIndex;
        });
    }

    // Reset sort dropdown to Relevance for new searches
    const sortSelect = document.querySelector('.sort-select');
    if (sortSelect) sortSelect.value = 'relevance';
    window.currentSortBy = 'relevance';

    // Initialize pagination state for each source (10 items per page) - MUST BE BEFORE RENDERING
    window.paginationState = {
        sfdc: { currentPage: 1, itemsPerPage: 10 },
        jira: { currentPage: 1, itemsPerPage: 10 },
        slack: { currentPage: 1, itemsPerPage: 10 },
        kcs: { currentPage: 1, itemsPerPage: 10 },
        github: { currentPage: 1, itemsPerPage: 10 },
        gitlab: { currentPage: 1, itemsPerPage: 10 }
    };

    // Initialize active product filters (empty Set means show all)
    window.activeProductFilters = new Set();

    // Render SFDC/Salesforce results
    renderSFDCResults(results.sfdc || {cases: [], total: 0});

    // Render Jira/OHSS results
    renderJiraResults(results.jira || {issues: [], total: 0});

    // Render Slack results
    renderSlackResults(results.slack || {messages: [], total: 0});
    syncSlackChannelsFromResults(results.slack?.messages);

    // Render KCS results
    renderKCSResults(results.kcs || {articles: [], total: 0});

    // Render GitHub results
    renderGitHubResults(results.github || {results: [], total: 0});

    // Render GitLab results
    renderGitLabResults(results.gitlab || {results: [], total: 0});

    // Auto-expand sections that have results
    const sourcesWithResults = [];
    if (results.sfdc?.cases?.length > 0) sourcesWithResults.push('salesforce');
    if (results.jira?.issues?.length > 0) sourcesWithResults.push('ohss');
    if (results.slack?.messages?.length > 0) sourcesWithResults.push('slack');
    if (results.kcs?.articles?.length > 0) sourcesWithResults.push('kcs');
    if (results.github?.results?.length > 0) sourcesWithResults.push('github');
    if (results.gitlab?.results?.length > 0) sourcesWithResults.push('gitlab');

    // Expand sections with results (only if their source filter is checked)
    sourcesWithResults.forEach(source => {
        const resultsSection = document.querySelector(`.results-section[data-source="${source}"]`);
        const sourceCheckbox = document.querySelector(`.source-filter[data-source="${source}"]`);
        const isChecked = sourceCheckbox ? sourceCheckbox.checked : true;
        if (resultsSection && isChecked) {
            resultsSection.classList.remove('collapsed');
            console.log(`  ✅ Auto-expanded ${source} section (has ${
                source === 'salesforce' ? results.sfdc.cases.length :
                source === 'ohss' ? results.jira.issues.length :
                source === 'slack' ? results.slack.messages.length :
                source === 'kcs' ? results.kcs.articles.length :
                source === 'github' ? results.github.results.length :
                results.gitlab.results.length
            } results)`);
        }
    });

    // Update total count in filters
    updateTotalCount(results);

    // Update visibility of results header and pagination
    updateSearchResultsDisplay();

    // Update section visibility based on filter checkboxes
    updateResultsVisibility();

    // Update product filter counts based on results
    updateProductCounts();

    // Auto-select products in filter based on search query
    autoSelectProductsFromQuery(query);

    // Debug: Log what we stored
    console.log('📦 Stored search results:', {
        sfdc: results.sfdc?.cases?.length || 0,
        jira: results.jira?.issues?.length || 0,
        slack: results.slack?.messages?.length || 0
    });

    // Add click listeners to result items for detail panel
    setTimeout(() => {
        addResultClickListeners();
    }, 100);

    // Pre-fetch Related Content for all SFDC tickets with OHSS trackers (background)
    setTimeout(() => {
        prefetchRelatedContentForSFDC(results);
    }, 200);

    console.log(`✅ Search complete! Found ${totalResults} total results across all sources`);
}

// Pre-fetch Related Content for Salesforce tickets in the background
async function prefetchRelatedContentForSFDC(results) {
    if (!results.sfdc || !results.sfdc.cases || results.sfdc.cases.length === 0) {
        return;
    }

    console.log('🔄 Pre-fetching Related Content for SFDC tickets...');

    // Collect unique OHSS ticket keys from all SFDC cases using external_trackers field
    const ohssKeys = new Set();

    for (const sfdcCase of results.sfdc.cases) {
        // external_trackers is already in the search results from backend
        const trackers = sfdcCase.external_trackers;

        if (trackers && Array.isArray(trackers) && trackers.length > 0) {
            console.log(`📋 Case ${sfdcCase.case_number} has ${trackers.length} external trackers:`, trackers);

            trackers.forEach(tracker => {
                // Trackers can be strings like "OHSS-12345" or objects
                let trackerKey = '';

                if (typeof tracker === 'string') {
                    trackerKey = tracker;
                } else if (tracker && typeof tracker === 'object') {
                    trackerKey = tracker.resourceKey || tracker.key || tracker.name || '';
                }

                if (trackerKey && trackerKey.startsWith('OHSS-')) {
                    ohssKeys.add(trackerKey);
                    console.log(`   ✅ Found OHSS tracker: ${trackerKey}`);
                }
            });
        }
    }

    if (ohssKeys.size === 0) {
        console.log('💤 No OHSS tickets found in SFDC results, skipping pre-fetch');
        return;
    }

    console.log(`🚀 Pre-fetching Related Content for ${ohssKeys.size} unique OHSS tickets: ${Array.from(ohssKeys).join(', ')}`);

    // Fetch Related Content for each unique OHSS ticket
    const fetchPromises = Array.from(ohssKeys).map(async (ohssKey) => {
        // Skip if already cached
        if (relatedContentCache.ohss[ohssKey]) {
            console.log(`💾 ${ohssKey} already cached, skipping`);
            return;
        }

        try {
            console.log(`🔗 Fetching Related Content for ${ohssKey}...`);
            const response = await fetch(`/api/jira-issue-links/${ohssKey}`, {
                method: 'GET',
                credentials: 'include'
            });

            if (!response.ok) {
                console.error(`❌ Failed to fetch ${ohssKey}: ${response.status}`);
                return;
            }

            const ohssData = await response.json();

            // Cache the data
            relatedContentCache.ohss[ohssKey] = {
                kcs_articles: ohssData.kcs_articles || [],
                slack_threads: ohssData.slack_threads || []
            };

            console.log(`✅ Pre-fetched and cached Related Content for ${ohssKey}:`, {
                kcs: ohssData.kcs_articles?.length || 0,
                slack: ohssData.slack_threads?.length || 0
            });
        } catch (err) {
            console.error(`❌ Error pre-fetching ${ohssKey}:`, err);
        }
    });

    // Run all fetches in parallel
    await Promise.all(fetchPromises);
    console.log('✅ Pre-fetch complete! Cached data:', relatedContentCache.ohss);
}

// Pagination helper functions
function createPaginationControls(source, totalItems) {
    if (!window.paginationState || !window.paginationState[source]) return '';

    const state = window.paginationState[source];
    const totalPages = Math.ceil(totalItems / state.itemsPerPage);

    if (totalPages <= 1) return ''; // No pagination needed

    let html = '<div class="pagination-controls">';

    // Previous button
    html += `<button class="pagination-btn" ${state.currentPage === 1 ? 'disabled' : ''} onclick="changePage('${source}', ${state.currentPage - 1})">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
        Previous
    </button>`;

    // Page numbers
    html += '<div class="pagination-pages">';

    // Always show first page
    if (state.currentPage > 3) {
        html += `<button class="pagination-page" onclick="changePage('${source}', 1)">1</button>`;
        if (state.currentPage > 4) {
            html += '<span class="pagination-ellipsis">...</span>';
        }
    }

    // Show pages around current page
    for (let i = Math.max(1, state.currentPage - 2); i <= Math.min(totalPages, state.currentPage + 2); i++) {
        html += `<button class="pagination-page ${i === state.currentPage ? 'active' : ''}" onclick="changePage('${source}', ${i})">${i}</button>`;
    }

    // Always show last page
    if (state.currentPage < totalPages - 2) {
        if (state.currentPage < totalPages - 3) {
            html += '<span class="pagination-ellipsis">...</span>';
        }
        html += `<button class="pagination-page" onclick="changePage('${source}', ${totalPages})">${totalPages}</button>`;
    }

    html += '</div>';

    // Next button
    html += `<button class="pagination-btn" ${state.currentPage === totalPages ? 'disabled' : ''} onclick="changePage('${source}', ${state.currentPage + 1})">
        Next
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
    </button>`;

    html += '</div>';

    return html;
}

function changePage(source, page) {
    if (!window.paginationState || !window.paginationState[source]) return;

    window.paginationState[source].currentPage = page;

    // Re-render the specific source results
    if (!window.lastSearchResults) return;

    switch(source) {
        case 'sfdc':
            renderSFDCResults(window.lastSearchResults.sfdc || {cases: [], total: 0});
            break;
        case 'jira':
            renderJiraResults(window.lastSearchResults.jira || {issues: [], total: 0});
            break;
        case 'slack':
            renderSlackResults(window.lastSearchResults.slack || {messages: [], total: 0});
            break;
        case 'kcs':
            renderKCSResults(window.lastSearchResults.kcs || {docs: [], total: 0});
            break;
        case 'github':
            renderGitHubResults(window.lastSearchResults.github || {results: [], total: 0});
            break;
        case 'gitlab':
            renderGitLabResults(window.lastSearchResults.gitlab || {results: [], total: 0});
            break;
    }

    // Scroll to the section
    const section = document.querySelector(`[data-source="${source === 'jira' ? 'ohss' : source}"]`);
    if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function getPaginatedItems(items, source) {
    if (!items) return items;

    // If pagination state doesn't exist, return items unpaginated
    if (!window.paginationState || !window.paginationState[source]) {
        console.warn(`⚠️ Pagination state not found for ${source}, returning all items`);
        return items;
    }

    const state = window.paginationState[source];

    // Apply product filter before pagination (for sources that support it)
    let filteredItems = items;
    if (source === 'sfdc' && window.activeProductFilters && window.activeProductFilters.size > 0) {
        filteredItems = items.filter(item => {
            const productTag = extractProductTag(item.product);
            return productTag && window.activeProductFilters.has(productTag);
        });
    }

    // Prioritize known products (ROSA, ARO, OSD, etc.) to the top for SFDC
    if (source === 'sfdc') {
        filteredItems = [...filteredItems].sort((a, b) => {
            const aTag = extractProductTag(a.product);
            const bTag = extractProductTag(b.product);
            if (aTag && !bTag) return -1;
            if (!aTag && bTag) return 1;
            return 0;
        });
    }

    // Always paginate the (possibly filtered) results
    const startIndex = (state.currentPage - 1) * state.itemsPerPage;
    const endIndex = startIndex + state.itemsPerPage;

    return filteredItems.slice(startIndex, endIndex);
}

function getFilteredItemCount(items, source) {
    if (!items) return 0;

    if (source === 'sfdc' && window.activeProductFilters && window.activeProductFilters.size > 0) {
        return items.filter(item => {
            const productTag = extractProductTag(item.product);
            return productTag && window.activeProductFilters.has(productTag);
        }).length;
    }

    return items.length;
}

// Render SFDC/Salesforce results
// Lazy load details for visible SFDC results (pagination-aware)
function lazyLoadVisibleSFDCDetails(visibleCases) {
    console.log(`⏳ Lazy loading details for ${visibleCases.length} visible SFDC cases...`);

    // Fetch details for each visible case in parallel
    const fetchPromises = visibleCases.map(caseItem => {
        return fetch(`/api/sfdc/case/${caseItem.case_number}`)
            .then(response => response.json())
            .then(details => {
                // Update the case in lastSearchResults
                if (window.lastSearchResults?.sfdc?.cases) {
                    const caseIndex = window.lastSearchResults.sfdc.cases.findIndex(
                        c => c.case_number === caseItem.case_number
                    );
                    if (caseIndex !== -1) {
                        // Merge details into the case
                        window.lastSearchResults.sfdc.cases[caseIndex] = {
                            ...window.lastSearchResults.sfdc.cases[caseIndex],
                            ...details
                        };
                    }
                }

                // Update the UI for this specific case
                const resultItem = document.querySelector(`[data-case-number="${caseItem.case_number}"]`);
                if (resultItem) {
                    const detailsDiv = resultItem.querySelector('.result-details');
                    if (detailsDiv) {
                        // Update SBR in the search result
                        detailsDiv.innerHTML = `
                            <strong>Status:</strong> ${caseItem.status || 'Unknown'} &nbsp;&nbsp;&nbsp;&nbsp;
                            <strong>Severity:</strong> ${caseItem.severity || 'N/A'} &nbsp;&nbsp;&nbsp;&nbsp;
                            <strong>Product:</strong> ${caseItem.product || 'N/A'} &nbsp;&nbsp;&nbsp;&nbsp;
                            <strong>SBR:</strong> ${details.sbr || 'N/A'}
                        `;
                    }
                }

                console.log(`  ✅ Loaded details for case ${caseItem.case_number}: SBR=${details.sbr}`);
                return details;
            })
            .catch(error => {
                console.error(`  ❌ Failed to load details for case ${caseItem.case_number}:`, error);
                return null;
            });
    });

    // Wait for all to complete
    Promise.all(fetchPromises).then(results => {
        const successCount = results.filter(r => r !== null).length;
        console.log(`✅ Lazy loading complete: ${successCount}/${visibleCases.length} cases enriched`);
    });
}

function renderSFDCResults(sfdc) {
    console.log('🔍 renderSFDCResults called with:', sfdc);
    console.log(`   Cases count: ${sfdc.cases?.length || 0}, Total: ${sfdc.total || 0}`);
    if (sfdc.error) {
        console.error('❌ SFDC search error:', sfdc.error);
    }

    const section = document.querySelector('[data-source="salesforce"] .section-content');
    if (!section) {
        console.error('❌ Salesforce section not found!');
        return;
    }

    const count = sfdc.cases?.length || 0;

    // Update BOTH section header AND filter count
    const headerElement = document.getElementById('sfdc-count');
    const filterElement = document.getElementById('filter-sfdc-count');

    if (headerElement) {
        headerElement.textContent = `Salesforce Tickets (${count})`;
        console.log(`✅ Updated SFDC section header: ${count}`);
    }

    if (filterElement) {
        filterElement.textContent = `(${count})`;
        console.log(`✅ Updated SFDC filter count: ${count}`);
    }

    if (!sfdc.cases || sfdc.cases.length === 0) {
        if (sfdc.error) {
            section.innerHTML = `<p class="no-results" style="color: #d32f2f;">Error searching Salesforce: ${sfdc.error}</p>`;
        } else {
            section.innerHTML = '<p class="no-results">No Salesforce cases found</p>';
        }
        return;
    }

    console.log(`✅ Rendering ${count} SFDC cases`);

    // Get paginated items (with product filter applied)
    const paginatedCases = getPaginatedItems(sfdc.cases, 'sfdc');
    const totalItems = getFilteredItemCount(sfdc.cases, 'sfdc');

    console.log(`📄 Pagination Debug - Total: ${sfdc.cases.length}, Filtered: ${totalItems}, Paginated: ${paginatedCases.length}, Page: ${window.paginationState?.sfdc?.currentPage || 'N/A'}`);

    section.innerHTML = paginatedCases.map((caseItem, index) => {
        const productTag = extractProductTag(caseItem.product);
        const dataProductAttr = productTag ? `data-product="${productTag}"` : '';

        // Debug first 3 items
        if (index < 3) {
            console.log(`🏷️ SFDC Case ${index + 1}:`, {
                caseNumber: caseItem.case_number,
                productRaw: caseItem.product,
                productTag: productTag
            });
        }

        return `
        <div class="result-item" ${dataProductAttr} data-case-number="${caseItem.case_number}">
            <div class="result-header">
                <div class="result-title">
                    <img src="/src/images/salesforce-logo.svg" class="result-icon" alt="Salesforce" />
                    ${caseItem.case_number} - ${caseItem.summary || 'No summary'}
                </div>
            </div>
            <div class="result-details">
                <strong>Status:</strong> ${caseItem.status || 'Unknown'} &nbsp;&nbsp;&nbsp;&nbsp; <strong>Severity:</strong> ${caseItem.severity || 'N/A'} &nbsp;&nbsp;&nbsp;&nbsp; <strong>Product:</strong> ${caseItem.product || 'N/A'} &nbsp;&nbsp;&nbsp;&nbsp; <strong>SBR:</strong> ${caseItem.sbr || 'N/A'}
            </div>
            ${caseItem.urls ? `
                <div class="sfdc-view-links">
                    <a href="${caseItem.urls.caseview_plus}" target="_blank" class="view-link caseview">CaseView+</a>
                    <a href="${caseItem.urls.classic}" target="_blank" class="view-link classic">Classic</a>
                    <a href="${caseItem.urls.customer_portal}" target="_blank" class="view-link portal">Customer Portal</a>
                </div>
            ` : `
                <a href="${caseItem.url}" target="_blank" class="view-link portal">View Case</a>
            `}
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('sfdc', totalItems);

    // Update section header with actual displayed count, filter with total
    updateSectionHeader('salesforce', sfdc.cases.length, sfdc.total);

    // Lazy load details for visible results (pagination-aware)
    lazyLoadVisibleSFDCDetails(paginatedCases);
}

// Render Jira/OHSS results
function renderJiraResults(jira) {
    console.log('🎯 renderJiraResults called with', jira.issues?.length || 0, 'issues');
    const section = document.querySelector('[data-source="ohss"] .section-content');
    if (!section) {
        console.error('❌ OHSS section not found!');
        return;
    }

    const count = jira.issues?.length || 0;
    const headerElement = document.getElementById('jira-count');
    const filterElement = document.getElementById('filter-jira-count');

    if (headerElement) headerElement.textContent = `Jira Tickets (${count})`;
    if (filterElement) filterElement.textContent = `(${count})`;

    if (!jira.issues || jira.issues.length === 0) {
        // Show error message if credentials are not configured
        if (jira.error && jira.error.includes('credentials')) {
            section.innerHTML = `
                <div class="no-results" style="padding: 20px; background: #fff3cd; border-left: 4px solid #ffc107; color: #856404;">
                    <strong>⚠️ Jira Search Not Available</strong>
                    <p style="margin-top: 8px;">Jira credentials are not configured. Please configure your Atlassian credentials in Settings.</p>
                    <a href="#" onclick="document.querySelector('.settings-btn').click(); return false;" style="color: #ee0000; text-decoration: underline;">Go to Settings</a>
                </div>
            `;
        } else {
            section.innerHTML = '<p class="no-results">No Jira issues found</p>';
        }
        return;
    }

    // Get paginated items
    const paginatedIssues = getPaginatedItems(jira.issues, 'jira');
    const totalItems = jira.issues.length;

    section.innerHTML = paginatedIssues.map(issue => {
        const productTag = extractProductTag(issue.product);
        const dataProductAttr = productTag ? `data-product="${productTag}"` : '';
        return `
        <div class="result-item" ${dataProductAttr} data-jira-key="${issue.key}">
            <div class="result-header">
                <div class="result-title">
                    <img src="/src/images/atlassian-jira.svg" class="result-icon" alt="Jira" />
                    ${issue.key} - ${issue.summary || 'No summary'}
                </div>
            </div>
            <div class="result-meta" style="display: flex; gap: 20px; margin: 8px 0; font-size: 14px; color: #666;">
                <span><strong>Project:</strong> ${issue.project_name || issue.project || 'N/A'}</span>
                <span><strong>Priority:</strong> ${issue.priority || 'N/A'}</span>
                <span><strong>Status:</strong> ${issue.status || 'Unknown'}</span>
                <span><strong>Work Type:</strong> ${issue.work_type || issue.type || 'N/A'}</span>
            </div>
            <a href="${issue.url}" target="_blank" class="view-link atlassian">View Jira</a>
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('jira', totalItems);

    updateSectionHeader('ohss', jira.issues.length, jira.total);
}

// Format Slack message text to HTML with proper rendering of mentions, links, and formatting
function formatSlackMessage(text) {
    if (!text) return '';
    // HTML-escape first to prevent XSS
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    // Slack mentions: <@USERID|DisplayName> → @DisplayName (bold)
    html = html.replace(/&lt;@[A-Z0-9]+\|([^&]+)&gt;/g, '<strong class="slack-mention">@$1</strong>');
    // Slack mentions without display name: <@USERID> → @user
    html = html.replace(/&lt;@([A-Z0-9]+)&gt;/g, '<strong class="slack-mention">@$1</strong>');
    // Slack subteam/group mentions: <!subteam^ID|@handle> → @handle
    html = html.replace(/&lt;!subteam\^[A-Z0-9]+\|@?([^&]+)&gt;/g, '<strong class="slack-mention">@$1</strong>');
    // Slack subteam without handle: <!subteam^ID> → @ID
    html = html.replace(/&lt;!subteam\^([A-Z0-9]+)&gt;/g, '<strong class="slack-mention">@$1</strong>');
    // Slack channel refs: <#CHANNELID|channel-name> → #channel-name
    html = html.replace(/&lt;#[A-Z0-9]+\|([^&]+)&gt;/g, '<strong>#$1</strong>');
    // Slack channel refs without name: <#CHANNELID> → #CHANNELID
    html = html.replace(/&lt;#([A-Z0-9]+)&gt;/g, '<strong>#$1</strong>');
    // Slack links with label: <URL|label> → clickable link
    html = html.replace(/&lt;(https?:\/\/[^|&]+)\|([^&]+)&gt;/g, '<a href="$1" target="_blank" class="slack-inline-link">$2</a>');
    // Slack bare links: <URL> → clickable link
    html = html.replace(/&lt;(https?:\/\/[^&]+)&gt;/g, '<a href="$1" target="_blank" class="slack-inline-link">$1</a>');
    // Bold: *text* → <strong>text</strong>
    html = html.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
    // Italic: _text_ → <em>text</em>
    html = html.replace(/\b_([^_\n]+)_\b/g, '<em>$1</em>');
    // Strikethrough: ~text~ → <del>text</del>
    html = html.replace(/~([^~\n]+)~/g, '<del>$1</del>');
    // Code inline: `text` → <code>text</code>
    html = html.replace(/`([^`\n]+)`/g, '<code class="slack-inline-code">$1</code>');
    // Newlines to <br>
    html = html.replace(/\n/g, '<br>');
    return html;
}

// Toggle expand/collapse for a Slack message card
function toggleSlackMessage(event, msgId) {
    event.stopPropagation();
    const collapsed = document.getElementById(msgId + '-collapsed');
    const full = document.getElementById(msgId + '-full');
    const btn = event.currentTarget;
    if (!collapsed || !full) return;
    const isCollapsed = btn.getAttribute('data-state') === 'collapsed';
    if (isCollapsed) {
        collapsed.style.display = 'none';
        full.style.display = 'block';
        btn.textContent = 'Show less';
        btn.setAttribute('data-state', 'expanded');
    } else {
        collapsed.style.display = 'block';
        full.style.display = 'none';
        btn.textContent = 'Show more';
        btn.setAttribute('data-state', 'collapsed');
    }
}

// Render Slack results
function renderSlackResults(slack) {
    console.log('🔍 renderSlackResults called with:', slack);
    console.log('   Messages count:', slack.messages?.length || 0);

    const section = document.querySelector('[data-source="slack"] .section-content');
    if (!section) {
        console.error('❌ Slack section not found!');
        return;
    }

    const count = slack.messages?.length || 0;
    const headerElement = document.getElementById('slack-count');
    const filterElement = document.getElementById('filter-slack-count');

    if (headerElement) headerElement.textContent = `Slack Threads (${count})`;
    if (filterElement) filterElement.textContent = `(${count})`;

    if (!slack.messages || slack.messages.length === 0) {
        section.innerHTML = '<p class="no-results">No Slack messages found</p>';
        console.log('⚠️ No Slack messages to render');
        return;
    }

    console.log(`✅ Rendering ${count} Slack messages`);

    // Get paginated items
    const paginatedMessages = getPaginatedItems(slack.messages, 'slack');
    const totalItems = slack.messages.length;

    section.innerHTML = paginatedMessages.map((msg, idx) => {
        const messageText = msg.text || '';
        const lines = messageText.split('\n');
        const firstThreeLines = lines.slice(0, 3).join('\n');
        const hasMore = lines.length > 3;
        const formattedPreview = formatSlackMessage(firstThreeLines) + (hasMore ? '<span class="slack-ellipsis">...</span>' : '');
        const formattedFull = formatSlackMessage(messageText);

        // Get reply count
        const replyCount = msg.reply_count || 0;

        const channelId = msg.channel_id || msg.channel || '';
        const threadTs = msg.thread_ts || msg.ts || '';
        const msgId = `slack-msg-${idx}-${threadTs.replace('.', '-')}`;

        return `
        <div class="result-item slack-message" data-channel-id="${channelId}" data-thread-ts="${threadTs}" data-msg-id="${msgId}">
            <div class="result-header" style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                <img src="/src/images/slack_logo_icon.svg" class="result-icon" alt="Slack" style="width: 20px; height: 20px;" />
                <span style="font-weight: 600; color: #333;">#${msg.channel_name || msg.channel || 'unknown'}</span>
                <span style="color: #999; font-size: 0.875rem;">•</span>
                <span style="font-weight: 600; color: #1264a3; font-size: 0.9rem;">${msg.user || 'Unknown User'}</span>
                <span style="color: #999; font-size: 0.875rem;">•</span>
                <span style="color: #666; font-size: 0.8125rem;">${msg.timestamp || ''}</span>
            </div>
            <div class="slack-message-body">
                <div class="slack-collapsed-text" id="${msgId}-collapsed">
                    ${formattedPreview}
                </div>
                ${hasMore ? `
                <div class="slack-full-text" id="${msgId}-full" style="display: none;">
                    ${formattedFull}
                </div>
                <button class="slack-toggle-btn" onclick="toggleSlackMessage(event, '${msgId}')" data-state="collapsed">
                    Show more
                </button>
                ` : ''}
            </div>
            <div style="margin-top: 0.75rem; display: flex; gap: 0.75rem; align-items: center;">
                ${replyCount > 0 ? `
                    <button class="view-thread-btn" onclick="viewSlackThread(event, '${channelId}', '${threadTs}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
                        </svg>
                        View ${replyCount} ${replyCount === 1 ? 'Reply' : 'Replies'}
                    </button>
                ` : ''}
                <a href="${msg.permalink}" target="_blank" class="slack-open-link">
                    Open in Slack
                </a>
            </div>
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('slack', totalItems);

    // Expand the section since we have results
    const resultsSection = document.querySelector('[data-source="slack"]');
    if (resultsSection && count > 0) {
        resultsSection.classList.remove('collapsed');
        console.log('✅ Expanded Slack section');
    }
}

// View Slack thread in Details panel
async function viewSlackThread(event, channelId, threadTs) {
    event.stopPropagation(); // Prevent card click
    event.preventDefault();

    console.log(`🧵 Fetching Slack thread: channel=${channelId}, thread_ts=${threadTs}`);

    const detailsPanel = document.querySelector('.detail-panel');
    const detailsTitle = detailsPanel?.querySelector('.detail-title');
    const overviewContent = detailsPanel?.querySelector('.tab-content[data-tab-content="overview"]');

    if (!detailsPanel || !overviewContent) {
        console.error('❌ Detail panel not found');
        return;
    }

    // Show details panel with loading state
    detailsPanel.classList.add('open', 'expanded');
    if (detailsTitle) detailsTitle.textContent = 'Slack Thread';

    // Hide non-relevant tabs
    const secondTab = detailsPanel.querySelector('.detail-tab[data-tab="escalation-ohss"]');
    const relatedTab = detailsPanel.querySelector('.detail-tab[data-tab="related-content"]');
    if (secondTab) secondTab.style.display = 'none';
    if (relatedTab) relatedTab.style.display = 'none';

    // Set source icon
    const sourceIcon = detailsPanel.querySelector('.source-icon');
    if (sourceIcon) sourceIcon.src = '/src/images/slack_logo_icon.svg';

    overviewContent.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner"></div><p>Loading thread...</p></div>';

    try {
        const response = await fetch('/api/slack-thread', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                channel_id: channelId,
                thread_ts: threadTs,
                config: {
                    slack_xoxc: localStorage.getItem('slack_xoxc') || sessionStorage.getItem('slack_xoxc'),
                    slack_xoxd: localStorage.getItem('slack_xoxd') || sessionStorage.getItem('slack_xoxd')
                }
            })
        });

        const result = await response.json();

        if (!result.success || !result.messages || result.messages.length === 0) {
            overviewContent.innerHTML = `
                <div style="padding: 1rem; color: #cc0000;">
                    <p>Failed to load thread: ${result.error || 'No messages found'}</p>
                </div>
            `;
            return;
        }

        console.log(`✅ Loaded ${result.messages.length} messages in thread`);

        const messagesHtml = result.messages.map((msg, index) => `
            <div style="border-bottom: 1px solid #e0e0e0; padding: 1rem; ${msg.is_parent ? 'background: #f5f5f5;' : ''}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <strong style="color: #611f69;">${msg.user}</strong>
                        ${msg.is_parent ? '<span style="background: #611f69; color: white; padding: 0.125rem 0.5rem; border-radius: 12px; font-size: 0.75rem;">Original Post</span>' : ''}
                    </div>
                    <span style="color: #999; font-size: 0.875rem;">${msg.timestamp}</span>
                </div>
                <div style="white-space: pre-wrap; line-height: 1.5; color: #333;">
                    ${msg.text || '<em>No text</em>'}
                </div>
            </div>
        `).join('');

        overviewContent.innerHTML = `
            <div style="max-height: calc(100vh - 200px); overflow-y: auto;">
                ${messagesHtml}
            </div>
            <div style="padding: 1rem; background: #f9f9f9; border-top: 2px solid #e0e0e0;">
                <p style="margin: 0; color: #666; font-size: 0.875rem;">
                    ${result.total} message${result.total === 1 ? '' : 's'} in thread
                </p>
            </div>
        `;

    } catch (error) {
        console.error('❌ Error fetching Slack thread:', error);
        overviewContent.innerHTML = `
            <div style="padding: 1rem; color: #cc0000;">
                <p>Error loading thread: ${error.message}</p>
            </div>
        `;
    }
}

// Render KCS results
// Lazy load details for visible KCS articles (pagination-aware)
function lazyLoadVisibleKCSDetails(visibleArticles) {
    console.log(`⏳ Lazy loading details for ${visibleArticles.length} visible KCS articles...`);

    // Fetch details for each visible article in parallel
    const fetchPromises = visibleArticles.map(article => {
        const articleId = article.id || article.documentKind;

        return fetch('/api/kcs-article-details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: articleId,
                url: article.url || article.view_uri,
                document_kind: article.document_kind,
                config: {
                    redhat_token: localStorage.getItem('redhat_token') || sessionStorage.getItem('redhat_token')
                }
            })
        })
            .then(response => response.json())
            .then(details => {
                // Update the article in lastSearchResults
                if (window.lastSearchResults?.kcs?.articles) {
                    const articleIndex = window.lastSearchResults.kcs.articles.findIndex(
                        a => (a.id || a.documentKind) === articleId
                    );
                    if (articleIndex !== -1) {
                        // Merge details into the article
                        window.lastSearchResults.kcs.articles[articleIndex] = {
                            ...window.lastSearchResults.kcs.articles[articleIndex],
                            environment: details.environment,
                            issue: details.issue,
                            resolution: details.resolution,
                            publish_state: details.publish_state,
                            abstract: details.abstract
                        };
                        console.log(`  💾 Saved enriched data for index ${articleIndex}:`, {
                            id: articleId,
                            environment: typeof details.environment === 'string' ? details.environment.substring(0, 50) : details.environment,
                            issue: typeof details.issue === 'string' ? details.issue.substring(0, 50) : (Array.isArray(details.issue) ? `[${details.issue.length} items]` : details.issue)
                        });
                    } else {
                        console.error(`  ❌ Could not find article ${articleId} in lastSearchResults (index: ${articleIndex})`);
                    }
                } else {
                    console.error(`  ❌ lastSearchResults.kcs.articles not available`);
                }

                console.log(`  ✅ Loaded details for KCS ${articleId}: Has Environment=${!!details.environment}, Issue=${!!details.issue}, Resolution=${!!details.resolution}`);
                return details;
            })
            .catch(error => {
                console.error(`  ❌ Failed to load details for KCS ${articleId}:`, error);
                return null;
            });
    });

    // Wait for all to complete
    Promise.all(fetchPromises).then(results => {
        const successCount = results.filter(r => r !== null).length;
        console.log(`✅ KCS lazy loading complete: ${successCount}/${visibleArticles.length} articles enriched`);
    });
}

function renderKCSResults(kcs) {
    const section = document.querySelector('[data-source="kcs"] .section-content');
    if (!section) return;

    const count = kcs.articles?.length || 0;
    const headerElement = document.getElementById('kcs-count');
    const filterElement = document.getElementById('filter-kcs-count');

    if (headerElement) headerElement.textContent = `KCS Articles (${count})`;
    if (filterElement) filterElement.textContent = `(${count})`;

    if (!kcs.articles || kcs.articles.length === 0) {
        section.innerHTML = '<p class="no-results">No KCS articles found</p>';
        return;
    }

    // Get paginated items
    const paginatedArticles = getPaginatedItems(kcs.articles, 'kcs');
    const totalItems = kcs.articles.length;

    section.innerHTML = paginatedArticles.map((article, index) => {
        const articleId = article.id || article.documentKind;
        return `
        <div class="result-item" data-kcs-index="${index}" data-kcs-id="${articleId}">
            <div class="result-header" style="margin-bottom: 0; border: none; border-bottom: none;">
                <div class="result-title" style="border: none; border-bottom: none; margin-bottom: 0;">
                    <img src="/src/images/Logo-Red_Hat-Hat_icon-Standard-RGB.svg" class="result-icon kcs-logo" alt="Red Hat" />
                    ${article.title || article.documentTitle || 'No title'}
                </div>
            </div>
            <div class="kcs-action-buttons" style="display: flex; gap: 0.5rem; margin-top: 0.75rem; border-top: none;">
                <a href="${article.url || article.view_uri}" target="_blank" class="view-link kcs-view-link" onclick="event.stopPropagation();">View KCS Article</a>
                <button class="view-link copy-kcs-link-btn" data-url="${article.url || article.view_uri}" onclick="event.stopPropagation(); copyKCSLink(this);">Copy KCS Article Link</button>
            </div>
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('kcs', totalItems);

    updateSectionHeader('kcs', kcs.articles.length, kcs.total);

    // Lazy load details for visible results (pagination-aware)
    lazyLoadVisibleKCSDetails(paginatedArticles);
}

// Render Red Hat Docs results
// Render GitHub results
function similarityBadge(score) {
    const pct = score != null ? Math.round(score * 100) : null;
    if (pct == null) return '';
    const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f59e0b' : '#94a3b8';
    return `<span class="badge" style="background:${color};color:#fff;margin-left:4px;">Similarity: ${pct}%</span>`;
}

function renderGitHubResults(github) {
    const section = document.querySelector('[data-source="github"] .section-content');
    if (!section) return;

    const count = github.results?.length || 0;
    const headerElement = document.getElementById('github-count');
    const filterElement = document.getElementById('filter-github-count');

    if (headerElement) headerElement.textContent = `GitHub Repository (${count})`;
    if (filterElement) filterElement.textContent = `(${count})`;

    if (!github.results || github.results.length === 0) {
        section.innerHTML = '<p class="no-results">No GitHub code found</p>';
        return;
    }

    // Get paginated items
    const paginatedResults = getPaginatedItems(github.results, 'github');
    const totalItems = github.results.length;

    section.innerHTML = paginatedResults.map(item => {
        const cleanUrl = item.url || (item.repository && item.path
            ? `https://github.com/${item.repository}/blob/master/${item.path}`
            : '#');

        return `
        <div class="result-item" data-global-idx="${item._originalIndex}">
            <div class="result-header">
                <div class="result-title">
                    <img src="/src/images/github_logo_icon.svg" class="result-icon" alt="GitHub" />
                    ${item.repository || 'Unknown repo'} / ${item.name || 'unknown file'}
                </div>
            </div>
            <div class="result-meta">
                ${item.language && item.language !== 'N/A' && item.language !== 'Unknown' ? `<span class="badge">${item.language}</span>` : ''}
                ${similarityBadge(item.similarity)}
            </div>
            <div class="result-path">${item.path || ''}</div>
            ${item.summary ? `<div class="result-description" style="margin-top:4px;color:#555;font-size:0.85em;">${item.summary}</div>` : ''}
            <a href="${cleanUrl}" target="_blank" class="view-link github-view">View on GitHub</a>
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('github', totalItems);

    updateSectionHeader('github', github.results.length, github.total);
}

// Render GitLab results
function renderGitLabResults(gitlab) {
    console.log('🔍 renderGitLabResults called with:', gitlab);
    console.log('   Results count:', gitlab.results?.length || 0, 'Total:', gitlab.total);

    const section = document.querySelector('[data-source="gitlab"] .section-content');
    if (!section) {
        console.warn('⚠️ GitLab section not found in DOM');
        return;
    }

    const count = gitlab.results?.length || 0;
    const headerElement = document.getElementById('gitlab-count');
    const filterElement = document.getElementById('filter-gitlab-count');

    if (headerElement) headerElement.textContent = `GitLab Repository (${count})`;
    if (filterElement) filterElement.textContent = `(${count})`;

    if (!gitlab.results || gitlab.results.length === 0) {
        section.innerHTML = '<p class="no-results">No GitLab code found</p>';
        return;
    }

    // Get paginated items
    const paginatedResults = getPaginatedItems(gitlab.results, 'gitlab');
    const totalItems = gitlab.results.length;

    section.innerHTML = paginatedResults.map(item => {
        const cleanUrl = item.url || '#';

        return `
        <div class="result-item" data-global-idx="${item._originalIndex}">
            <div class="result-header">
                <div class="result-title">
                    <img src="/src/images/gitlab-icon.svg" class="result-icon" alt="GitLab" />
                    ${item.project_name || 'Unknown project'} / ${item.filename || 'unknown file'}
                </div>
            </div>
            <div class="result-path">${item.path || ''}</div>
            <div class="result-description">${item.content_snippet ? item.content_snippet.substring(0, 200) : ''}</div>
            <a href="${cleanUrl}" target="_blank" class="view-link gitlab-view">View on GitLab</a>
        </div>
        `;
    }).join('');

    // Add pagination controls
    section.innerHTML += createPaginationControls('gitlab', totalItems);

    updateSectionHeader('gitlab', gitlab.results.length, gitlab.total);
}

// Update section header with result count
function updateSectionHeader(source, displayedCount, totalCount) {
    // If totalCount not provided, use displayedCount for both
    if (totalCount === undefined) {
        totalCount = displayedCount;
    }

    console.log(`📊 Updating ${source}: displayed=${displayedCount}, total=${totalCount}`);

    const section = document.querySelector(`.results-section[data-source="${source}"]`);
    if (!section) {
        console.warn(`⚠️ Section not found for source: ${source}`);
        return;
    }

    const header = section.querySelector('.section-title-text');
    if (header) {
        const baseText = header.textContent.replace(/\s*\(\d+\)\s*$/, '').trim();
        header.textContent = `${baseText} (${displayedCount})`;
    }

    // Update filter count in sidebar - ALSO show displayed count (same as section)
    const filterOption = document.querySelector(`.source-filter[data-source="${source}"]`);
    if (filterOption) {
        const filterCount = filterOption.parentElement.querySelector('.filter-count');
        if (filterCount) {
            filterCount.textContent = `(${displayedCount})`;
            console.log(`✅ Updated filter count for ${source}: (${displayedCount})`);
        }
    }

    // Expand section if it has results
    if (displayedCount > 0) {
        section.classList.remove('collapsed');
    }
}

// Update total count in "Select All" filter
function updateTotalCount(results) {
    // Use actual displayed counts, not total matches
    const total =
        (results.jira?.issues?.length || 0) +
        (results.sfdc?.cases?.length || 0) +
        (results.slack?.messages?.length || 0) +
        (results.kcs?.articles?.length || 0) +
        (results.github?.results?.length || 0) +
        (results.gitlab?.results?.length || 0);

    const selectAllCount = document.querySelector('.select-all-sources')?.parentElement?.querySelector('.filter-count');
    if (selectAllCount) {
        selectAllCount.textContent = `(${total})`;
    }
}
// Detail Panel Functionality
// Show detail panel when clicking on a result

// Helper function to construct clean GitHub/GitLab URLs without commit SHA
function constructCleanRepoUrl(resultData, source) {
    const isGitHub = source === 'github';

    if (isGitHub && resultData.repository && resultData.path) {
        // Use 'master' as default branch for GitHub
        const branch = 'master';
        return `https://github.com/${resultData.repository}/blob/${branch}/${resultData.path}`;
    } else if (!isGitHub && resultData.project_id && resultData.path) {
        const gitlabUrl = 'https://gitlab.cee.redhat.com';
        const branch = resultData.ref || 'main';
        return `${gitlabUrl}/${resultData.project_name || resultData.project_id}/-/blob/${branch}/${resultData.path}`;
    }

    // Fallback to original URL if we can't construct
    return resultData.url || '#';
}

function showDetailPanel(resultData, source) {
    console.log('🎯 showDetailPanel called with source:', source, 'data:', resultData);

    // Use the global detailPanel variable (declared at line 1860)
    if (!detailPanel) return;

    // Show the panel and auto-expand it
    detailPanel.classList.add('visible');
    detailPanel.classList.add('expanded');
    console.log('✅ Detail panel opened and expanded for source:', source);

    // Collapse the Filters panel when Details panel opens
    const filtersPanel = document.querySelector('.filters-panel');
    if (filtersPanel && !filtersPanel.classList.contains('collapsed')) {
        filtersPanel.classList.remove('expanded');
        filtersPanel.classList.add('collapsed');
        console.log('✅ Collapsed filters panel');
    }

    // For KCS articles, hide tabs, meta sections, and show simplified view
    const detailSummary = detailPanel.querySelector('.detail-summary');
    const detailTabs = detailPanel.querySelector('.detail-tabs');
    const escalationTab = detailPanel.querySelector('.tab-content[data-tab-content="escalation-ohss"]');
    const relatedContentSection = detailPanel.querySelector('.related-content');

    if (source === 'kcs' || source === 'github' || source === 'gitlab') {
        // Hide meta information, tabs, and related content for KCS/GitHub/GitLab
        if (detailSummary) detailSummary.style.display = 'none';
        if (detailTabs) detailTabs.style.display = 'none';
        if (escalationTab) escalationTab.style.display = 'none';
        if (relatedContentSection) relatedContentSection.style.display = 'none';
    } else {
        // Show everything for other sources (SFDC, Jira, Slack)
        if (detailSummary) detailSummary.style.display = 'block';
        if (detailTabs) detailTabs.style.display = 'flex';
        // Don't set inline display:block on escalationTab - let CSS .tab-content.active handle visibility
        if (escalationTab) escalationTab.style.display = '';
        if (relatedContentSection) relatedContentSection.style.display = 'block';

        // Clear Related Content section for all sources (will be populated dynamically if needed)
        const relatedTabs = detailPanel.querySelector('.related-tabs');
        const relatedItems = detailPanel.querySelector('.related-items');
        if (relatedTabs) relatedTabs.innerHTML = '';
        if (relatedItems) {
            if (source === 'ohss' || source === 'jira' || source === 'salesforce') {
                relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">Loading related content...</p>';
            } else {
                relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">No related content available</p>';
            }
        }

        // Hide/show KCS tab based on source
        const kcsTabs = detailPanel.querySelectorAll('.related-tab.kcs-tab');
        kcsTabs.forEach(tab => {
            if (source === 'ohss' || source === 'jira') {
                tab.style.display = 'none';
            } else {
                tab.style.display = '';
            }
        });

        // Show AI Summary tab only for Salesforce cases
        const aiTab = detailPanel.querySelector('.ai-tab');
        if (aiTab) {
            aiTab.style.display = source === 'salesforce' ? '' : 'none';
        }
        if (source === 'salesforce' && resultData.case_number) {
            setAIContext(resultData.case_number, resultData);
        } else {
            resetAISummaryPanel();
        }
    }

    // Update the header based on source
    const titleSection = detailPanel.querySelector('.detail-title-section');
    const detailTitle = detailPanel.querySelector('.detail-title');
    const sourceIcon = titleSection.querySelector('.source-icon');

    // Set icon based on source
    const iconMap = {
        'salesforce': '/src/images/salesforce-logo.svg',
        'ohss': '/src/images/atlassian-jira.svg',
        'jira': '/src/images/atlassian-jira.svg',  // All Jira tickets (OHSS, RFE, etc.)
        'slack': '/src/images/slack_logo_icon.svg',
        'kcs': '/src/images/Logo-Red_Hat-Hat_icon-Standard-RGB.svg',  // Match search results logo
        'github': '/src/images/github_logo_icon.svg',
        'gitlab': '/src/images/gitlab-icon.svg'
    };

    if (sourceIcon && iconMap[source]) {
        sourceIcon.src = iconMap[source];
    }

    // Update title based on source type
    if (source === 'salesforce') {
        detailTitle.textContent = `Salesforce Case #${resultData.case_number}`;
    } else if (source === 'ohss' || source === 'jira') {
        detailTitle.textContent = `Jira ${resultData.key}`;
    } else if (source === 'slack') {
        detailTitle.textContent = `Slack #${resultData.channel_name || resultData.channel || 'unknown'}`;
    } else if (source === 'kcs') {
        detailTitle.textContent = resultData.title || 'Article';
    } else if (source === 'github' || source === 'gitlab') {
        detailTitle.textContent = resultData.name || resultData.filename || 'Repository File';
    }

    // Update second tab label and visibility based on source
    const secondTab = detailPanel.querySelector('.detail-tab[data-tab="escalation-ohss"]');
    const relatedContentTab = detailPanel.querySelector('.detail-tab[data-tab="related-content"]');

    if (secondTab) {
        if (source === 'salesforce') {
            secondTab.textContent = 'Linked JIRA ticket';
            secondTab.style.display = 'block';
        } else if (source === 'ohss' || source === 'jira') {
            secondTab.textContent = 'Linked Salesforce ticket';
            secondTab.style.display = 'block';
        } else if (source === 'github' || source === 'gitlab' || source === 'slack' || source === 'kcs') {
            // Hide External Trackers tab for sources that don't have linked tickets
            secondTab.style.display = 'none';
        }
    }

    // Hide Related Content tab for sources that don't have related content
    if (relatedContentTab) {
        if (source === 'github' || source === 'gitlab' || source === 'slack') {
            relatedContentTab.style.display = 'none';
        } else {
            relatedContentTab.style.display = 'block';
        }
    }

    // Update summary section
    const summaryTitle = detailPanel.querySelector('.summary-title');
    if (summaryTitle) {
        summaryTitle.textContent = resultData.summary || resultData.title || resultData.text || 'No description';
    }

    // Update meta information using specific IDs
    if (source === 'salesforce') {
        // Reset labels to Salesforce labels
        const metaRows = detailPanel.querySelectorAll('.meta-row strong');
        const metaRowElements = detailPanel.querySelectorAll('.meta-row');

        if (metaRows.length >= 9) {
            // First column (5 rows)
            metaRows[0].textContent = 'Case Owner:';
            metaRows[1].textContent = 'Status:';
            metaRows[2].textContent = 'Internal Status:';
            metaRows[3].textContent = 'Account Number:';
            metaRows[4].textContent = 'Account Name:';

            // Second column (4 rows)
            metaRows[5].textContent = 'Product:';
            metaRows[6].textContent = 'Severity:';
            metaRows[7].textContent = 'SBT:';
            metaRows[8].textContent = 'SBR:';

            // Show all rows for SFDC
            for (let i = 0; i < metaRowElements.length; i++) {
                if (metaRowElements[i]) metaRowElements[i].style.display = '';
            }
        }

        // Show loading state first
        document.getElementById('detail-owner').textContent = 'Loading...';
        document.getElementById('detail-status').textContent = resultData.status || 'Unknown';
        document.getElementById('detail-internal-status').textContent = 'Loading...';
        document.getElementById('detail-account-number').textContent = 'Loading...';
        document.getElementById('detail-account-name').textContent = 'Loading...';

        // Second Column
        document.getElementById('detail-product').textContent = resultData.product || 'N/A';
        document.getElementById('detail-severity').textContent = resultData.severity || 'N/A';

        // Set loading state for SBT and SBR
        const sbtElement = document.getElementById('detail-sbt');
        sbtElement.textContent = 'Loading...';
        document.getElementById('detail-sbr').textContent = 'Loading...';

        // Lazy load full case details (use relative URL to avoid CORS)
        fetch(`/api/sfdc/case/${resultData.case_number}`)
            .then(response => response.json())
            .then(details => {
                // Update all the enriched fields
                document.getElementById('detail-owner').textContent = details.owner || 'N/A';
                document.getElementById('detail-internal-status').textContent = details.internal_status || 'N/A';
                document.getElementById('detail-account-number').textContent = details.account_number || 'N/A';
                document.getElementById('detail-account-name').textContent = details.account_name || 'N/A';
                document.getElementById('detail-sbr').textContent = details.sbr || 'N/A';

                // Format SBT with color coding
                const sbtValue = details.sbt;

                if (sbtValue && sbtValue !== 'N/A') {
                    // Try to parse as number first
                    const sbtNum = parseFloat(sbtValue);

                    if (!isNaN(sbtNum)) {
                        // Numeric SBT value
                        let colorClass = '';
                        let displayText = '';

                        if (sbtNum <= 0) {
                            // Red - Breached
                            colorClass = 'sbt-breached';
                            displayText = `${sbtNum} (Breached)`;
                        } else if (sbtNum <= 60) {
                            // Red - Critical (1-60 minutes)
                            colorClass = 'sbt-critical';
                            displayText = `${sbtNum} minutes`;
                        } else if (sbtNum <= 239) {
                            // Orange - Warning (61-239 minutes)
                            colorClass = 'sbt-warning';
                            displayText = `${sbtNum} minutes`;
                        } else {
                            // Green - Good (240+ minutes)
                            colorClass = 'sbt-good';
                            displayText = `${sbtNum} minutes`;
                        }

                        sbtElement.innerHTML = `<span class="${colorClass}">${displayText}</span>`;
                    } else {
                        // Non-numeric SBT value (text)
                        let colorClass = '';
                        const lowerValue = sbtValue.toLowerCase();

                        if (lowerValue.includes('not breached') || lowerValue.includes('not_breached')) {
                            // Green - Not Breached
                            colorClass = 'sbt-good';
                        } else if (lowerValue.includes('breached')) {
                            // Red - Breached
                            colorClass = 'sbt-breached';
                        } else {
                            // Default - no color for other text values
                            sbtElement.textContent = sbtValue;
                            return;
                        }

                        sbtElement.innerHTML = `<span class="${colorClass}">${sbtValue}</span>`;
                    }
                } else {
                    sbtElement.textContent = 'N/A';
                }
            })
            .catch(error => {
                console.error('Error loading SFDC case details:', error);
                // Show error state
                document.getElementById('detail-owner').textContent = 'Error loading';
                document.getElementById('detail-internal-status').textContent = 'Error loading';
                document.getElementById('detail-account-number').textContent = 'Error loading';
                document.getElementById('detail-account-name').textContent = 'Error loading';
                sbtElement.textContent = 'Error loading';
                document.getElementById('detail-sbr').textContent = 'Error loading';
            });
    } else if (source === 'ohss' || source === 'jira') {
        // Update labels for Jira tickets (OHSS, RFE, etc.)
        const metaRows = detailPanel.querySelectorAll('.meta-row strong');
        const metaRowElements = detailPanel.querySelectorAll('.meta-row');

        if (metaRows.length >= 9) {
            // First column (4 rows)
            metaRows[0].textContent = 'Assignee:';
            metaRows[1].textContent = 'Reporter:';
            metaRows[2].textContent = 'Status:';
            metaRows[3].textContent = 'Security Level:';

            // Hide row 4 (Account Name - SFDC only)
            if (metaRowElements[4]) metaRowElements[4].style.display = 'none';

            // Second column (4 rows) - use dynamic label from backend (Product or Project)
            const productLabel = resultData.product_label || 'Product';
            metaRows[5].textContent = `${productLabel}:`;
            metaRows[6].textContent = 'Priority:';
            metaRows[7].textContent = 'Work Type:';
            metaRows[8].textContent = 'Components:';

            // Show rows 5-8
            if (metaRowElements[5]) metaRowElements[5].style.display = '';
            if (metaRowElements[6]) metaRowElements[6].style.display = '';
            if (metaRowElements[7]) metaRowElements[7].style.display = '';
            if (metaRowElements[8]) metaRowElements[8].style.display = '';
        }

        // Populate OHSS fields
        // First Column (4 rows: Assignee, Reporter, Status, Security Level)
        document.getElementById('detail-owner').textContent = resultData.assignee || 'Unassigned';
        document.getElementById('detail-status').textContent = resultData.reporter || 'N/A';
        document.getElementById('detail-internal-status').textContent = resultData.status || 'Unknown';
        document.getElementById('detail-account-number').textContent = resultData.security_level || 'None';

        // Second Column (4 rows: Product, Priority, Work Type, Components)
        document.getElementById('detail-product').textContent = resultData.product || 'N/A';
        document.getElementById('detail-severity').textContent = resultData.priority || 'N/A';
        document.getElementById('detail-sbt').textContent = resultData.work_type || resultData.type || 'N/A';
        document.getElementById('detail-sbr').textContent = resultData.components || 'None';
    } else if (source === 'slack') {
        const metaRows = detailPanel.querySelectorAll('.meta-row strong');
        if (metaRows.length >= 9) {
            metaRows[0].textContent = 'User:';
            metaRows[1].textContent = 'Channel:';
            metaRows[2].textContent = 'Timestamp:';
            metaRows[3].textContent = 'Replies:';
            metaRows[4].textContent = '';

            metaRows[5].textContent = 'Open in Slack:';
            metaRows[6].textContent = '';
            metaRows[7].textContent = '';
            metaRows[8].textContent = '';
        }

        const channelName = resultData.channel_name || resultData.channel || 'unknown';
        document.getElementById('detail-owner').textContent = resultData.user || 'Unknown';
        document.getElementById('detail-status').textContent = `#${channelName}`;
        document.getElementById('detail-internal-status').textContent = resultData.timestamp || 'N/A';
        document.getElementById('detail-account-number').textContent = resultData.reply_count != null ? `${resultData.reply_count} replies` : 'N/A';

        const slackLinkEl = document.getElementById('detail-product');
        if (slackLinkEl && resultData.permalink) {
            slackLinkEl.innerHTML = `<a href="${resultData.permalink}" target="_blank" style="color: #611f69; text-decoration: none;">Open thread</a>`;
        } else {
            slackLinkEl.textContent = 'N/A';
        }
        document.getElementById('detail-severity').textContent = '';
        document.getElementById('detail-sbt').textContent = '';
        document.getElementById('detail-sbr').textContent = '';

        // Hide empty rows
        const metaRowElements = detailPanel.querySelectorAll('.meta-row');
        if (metaRowElements.length >= 9) {
            metaRowElements[4].style.display = 'none';
            metaRowElements[6].style.display = 'none';
            metaRowElements[7].style.display = 'none';
            metaRowElements[8].style.display = 'none';
        }
    } else if (source === 'github' || source === 'gitlab') {
        // Update labels for GitHub/GitLab
        const metaRows = detailPanel.querySelectorAll('.meta-row strong');
        if (metaRows.length >= 8) {
            if (source === 'github') {
                // First column
                metaRows[0].textContent = 'Repository:';
                metaRows[1].textContent = 'File:';
                metaRows[2].textContent = 'Language:';
                metaRows[3].textContent = 'Score:';

                // Second column
                metaRows[4].textContent = 'URL:';
                metaRows[5].textContent = 'SHA:';
                metaRows[6].textContent = 'Type:';
                metaRows[7].textContent = 'Source:';
            } else {
                // GitLab
                // First column
                metaRows[0].textContent = 'Project:';
                metaRows[1].textContent = 'File:';
                metaRows[2].textContent = 'Ref:';
                metaRows[3].textContent = 'Project ID:';

                // Second column
                metaRows[4].textContent = 'URL:';
                metaRows[5].textContent = 'Start Line:';
                metaRows[6].textContent = 'Type:';
                metaRows[7].textContent = 'Source:';
            }
        }

        // Populate GitHub/GitLab fields
        if (source === 'github') {
            // First Column
            document.getElementById('detail-owner').textContent = resultData.repository || 'N/A';
            document.getElementById('detail-status').textContent = resultData.path || resultData.name || 'N/A';
            document.getElementById('detail-internal-status').textContent = resultData.language || 'N/A';
            document.getElementById('detail-account-name').textContent = resultData.similarity != null ? Math.round(resultData.similarity * 100) + '%' : 'N/A';

            // Second Column
            const cleanUrl = constructCleanRepoUrl(resultData, 'github');
            const urlLink = cleanUrl !== '#' ? `<a href="${cleanUrl}" target="_blank" class="view-link github-view">View on GitHub</a>` : 'N/A';
            document.getElementById('detail-product').innerHTML = urlLink;
            document.getElementById('detail-severity').textContent = resultData.sha ? resultData.sha.substring(0, 8) : 'N/A';
            document.getElementById('detail-sbt').textContent = 'Code';
            document.getElementById('detail-sbr').textContent = 'GitHub';
        } else {
            // GitLab
            // First Column
            document.getElementById('detail-owner').textContent = resultData.project_name || resultData.project_id || 'N/A';
            document.getElementById('detail-status').textContent = resultData.filename || resultData.path || 'N/A';
            document.getElementById('detail-internal-status').textContent = resultData.ref || 'main';
            document.getElementById('detail-account-name').textContent = resultData.project_id || 'N/A';

            // Second Column - Use URL from backend
            const cleanUrl = resultData.url || '#';
            const urlLink = cleanUrl !== '#' ? `<a href="${cleanUrl}" target="_blank" class="view-link gitlab-view">View on GitLab</a>` : 'N/A';
            document.getElementById('detail-product').innerHTML = urlLink;
            document.getElementById('detail-severity').textContent = resultData.startline ? `Line ${resultData.startline}` : 'N/A';
            document.getElementById('detail-sbt').textContent = 'Code';
            document.getElementById('detail-sbr').textContent = 'GitLab';
        }
    } else if (source === 'kcs') {
        // Update labels for KCS articles
        const metaRows = detailPanel.querySelectorAll('.meta-row strong');
        if (metaRows.length >= 8) {
            // First column
            metaRows[0].textContent = 'Document Kind:';
            metaRows[1].textContent = 'Score:';
            metaRows[2].textContent = 'Article ID:';
            metaRows[3].textContent = 'Version:';

            // Second column
            metaRows[4].textContent = 'Product:';
            metaRows[5].textContent = 'Portal URL:';
            metaRows[6].textContent = 'Modified:';
            metaRows[7].textContent = 'Status:';
        }

        // Populate KCS fields
        // First Column
        document.getElementById('detail-owner').textContent = resultData.document_kind || 'Article';
        document.getElementById('detail-status').textContent = resultData.score ? resultData.score.toFixed(2) : 'N/A';
        document.getElementById('detail-internal-status').textContent = resultData.id || 'N/A';
        document.getElementById('detail-account-name').textContent = resultData.version || 'N/A';

        // Second Column
        document.getElementById('detail-product').textContent = resultData.product || 'N/A';
        document.getElementById('detail-severity').textContent = resultData.url ? 'Available' : 'N/A';
        document.getElementById('detail-sbt').textContent = resultData.modified_date || 'N/A';
        document.getElementById('detail-sbr').textContent = resultData.status || 'Published';
    }

    // Update detail content
    const sectionLabel = detailPanel.querySelector('.section-label');
    const sectionText = detailPanel.querySelector('.section-text');

    // Update section label based on source (skip for KCS as it uses custom layout)
    if (sectionLabel && source !== 'kcs') {
        if (source === 'salesforce') {
            sectionLabel.textContent = 'Issue Description';
        } else if (source === 'ohss' || source === 'jira') {
            sectionLabel.textContent = 'Description';
        } else if (source === 'slack') {
            sectionLabel.textContent = 'Message';
        } else if (source === 'github' || source === 'gitlab') {
            sectionLabel.textContent = 'Repository Information';
        } else {
            sectionLabel.textContent = 'Content';
        }
    }

    // Update section content
    if (source === 'github' || source === 'gitlab') {
        // For GitHub/GitLab, replace the entire overview tab content with repository details
        const overviewTabContent = detailPanel.querySelector('.tab-content[data-tab-content="overview"]');
        console.log(`🔍 ${source.toUpperCase()}: Found overview tab?`, !!overviewTabContent);

        if (overviewTabContent) {
            const isGitHub = source === 'github';

            // Use URL from backend
            const fileUrl = resultData.url || '#';

            // Format repository information
            const repoInfo = {
                name: isGitHub ? (resultData.repository || 'N/A') : (resultData.project_name || 'N/A'),
                file: resultData.filename || resultData.name || resultData.path || 'N/A',
                path: resultData.path || 'N/A',
                branch: resultData.ref || 'main',
                language: resultData.language || 'N/A',
                description: resultData.content_snippet || resultData.description || 'No description available'
            };
            const summaryText = resultData.summary || '';

            // Completely replace the overview tab content
            overviewTabContent.innerHTML = `
                <div class="kcs-sections" style="padding: 1.5rem;">
                    <div class="kcs-section">
                        <h4 class="kcs-section-title">Repository</h4>
                        <div class="kcs-section-text">${repoInfo.name}</div>
                    </div>

                    <div class="kcs-section">
                        <h4 class="kcs-section-title">File</h4>
                        <div class="kcs-section-text" style="font-family: 'Courier New', monospace;">${repoInfo.path}</div>
                    </div>

                    ${summaryText ? `
                    <div class="kcs-section">
                        <h4 class="kcs-section-title">Content Preview</h4>
                        <div class="kcs-section-text">${summaryText}</div>
                    </div>` : `
                    <div class="kcs-section">
                        <h4 class="kcs-section-title">Description</h4>
                        <div class="description-content">
                            <em style="color: #999;">Loading first 20 lines...</em>
                        </div>
                    </div>`}

                    <div class="kcs-action-buttons">
                        <a href="${fileUrl}" target="_blank" class="view-link ${isGitHub ? 'github-view' : 'gitlab-view'}">
                            View on ${isGitHub ? 'GitHub' : 'GitLab'}
                        </a>
                        <button class="view-link ${isGitHub ? 'copy-github-link-btn' : 'copy-gitlab-link-btn'}"
                                onclick="event.stopPropagation(); ${isGitHub ? 'copyGitHubLink' : 'copyGitLabLink'}(this)"
                                data-url="${fileUrl}">
                            Copy ${isGitHub ? 'GitHub' : 'GitLab'} Link
                        </button>
                    </div>
                </div>
            `;

            // Fetch file content asynchronously only if no local summary
            if (!summaryText) fetchFileDescription(resultData, source);
            console.log(`✅ ${source.toUpperCase()}: Replaced overview tab content with repository details`);
        } else {
            console.error(`❌ ${source.toUpperCase()}: Could not find overview tab content`);
        }
    } else if (source === 'kcs') {
        // For KCS, replace the entire overview tab content with Environment/Issue/Resolution
        const overviewTabContent = detailPanel.querySelector('.tab-content[data-tab-content="overview"]');
        console.log('🔍 KCS: Found overview tab?', !!overviewTabContent);

        if (overviewTabContent) {
            const articleUrl = resultData.url || resultData.view_uri || '#';

            // Debug: Log what data we have
            console.log('📋 KCS Article Data:', {
                environment: resultData.environment,
                issue: resultData.issue,
                resolution: resultData.resolution,
                abstract: resultData.abstract,
                product: resultData.product,
                version: resultData.version
            });

            // Helper function to format KCS content (preserve line breaks and basic formatting)
            const formatKCSContent = (content) => {
                if (!content) return 'N/A';

                // Convert to string if it's an array or object
                let textContent = content;
                if (Array.isArray(content)) {
                    textContent = content.join('\n');
                } else if (typeof content === 'object') {
                    textContent = JSON.stringify(content, null, 2);
                } else if (typeof content !== 'string') {
                    textContent = String(content);
                }

                // Clean up and format the text:
                // 1. Replace newlines with <br>
                textContent = textContent.replace(/\n/g, '<br>').replace(/\r/g, '');

                // 2. Add line breaks before bullet points that are stuck together (e.g., "item1- item2")
                textContent = textContent.replace(/([^\-])\-\s+([A-Z\[])/g, '$1<br>- $2');

                // 3. Ensure bullet points start on new lines
                textContent = textContent.replace(/^-\s+/gm, '- ');

                return textContent;
            };

            // Get brief resolution (first 500 characters)
            const getBriefResolution = (resolution) => {
                // Only use resolution if it exists - don't fall back to abstract/issue
                // because those are already shown in the Issue section
                let resText = resolution || '';

                if (!resText) return '<em>View full article for resolution details</em>';

                if (Array.isArray(resText)) {
                    resText = resText.join('\n');
                } else if (typeof resText !== 'string') {
                    resText = String(resText);
                }

                // Clean up the text
                resText = resText.trim();

                // If resolution is long, truncate and add link
                if (resText.length > 500) {
                    const truncated = resText.substring(0, 500).trim();
                    // Find the last complete sentence within the truncated text
                    const lastPeriod = truncated.lastIndexOf('.');
                    const finalText = lastPeriod > 300 ? truncated.substring(0, lastPeriod + 1) : truncated;
                    return formatKCSContent(finalText) + '...<br><br><em>View full article for complete resolution details</em>';
                }

                // If short enough, show it all with a note to view full article
                return formatKCSContent(resText) + '<br><br><em>View full article for complete details</em>';
            };

            // Format verification status
            const getVerificationStatus = (resultData) => {
                const docKind = resultData.document_kind || '';
                const verificationState = resultData.verification_state;
                const publishState = resultData.publish_state;

                // Debug: Log all status fields
                console.log('🔍 KCS Status Debug:', {
                    id: resultData.id,
                    document_kind: docKind,
                    verification_state: verificationState,
                    publish_state: publishState,
                    url: resultData.url
                });

                let statusClass = '';
                let displayText = '';

                // Check publish state first - unpublished overrides everything
                if (publishState && publishState.toLowerCase() === 'unpublished') {
                    statusClass = 'status-draft';
                    displayText = 'Unpublished';
                    return `<span class="kcs-status ${statusClass}">${displayText}</span>`;
                }

                // Map document_kind to status
                if (docKind.toLowerCase() === 'solution') {
                    statusClass = 'status-verified';
                    displayText = 'Solution Verified';
                } else if (docKind.toLowerCase() === 'article') {
                    statusClass = 'status-verified';
                    displayText = 'Published Article';
                } else if (verificationState && verificationState !== 'N/A') {
                    // Use verification_state if available
                    const statusLower = verificationState.toLowerCase();
                    if (statusLower.includes('verified')) {
                        statusClass = 'status-verified';
                        displayText = 'Solution Verified';
                    } else if (statusLower.includes('pending')) {
                        statusClass = 'status-pending';
                        displayText = 'Pending Verification';
                    } else if (statusLower.includes('draft')) {
                        statusClass = 'status-draft';
                        displayText = 'Draft';
                    } else {
                        displayText = verificationState;
                    }
                } else if (publishState && publishState !== 'N/A') {
                    statusClass = 'status-verified';
                    displayText = publishState;
                } else {
                    // Default fallback
                    statusClass = 'status-verified';
                    displayText = 'Published';
                }

                return `<span class="kcs-status ${statusClass}">${displayText}</span>`;
            };

            // Check if article details are already loaded (from lazy loading)
            const hasLoadedDetails = resultData.environment !== undefined || resultData.issue !== undefined || resultData.resolution !== undefined;

            console.log('🔍 KCS Details Check:', {
                hasLoadedDetails,
                hasEnvironment: !!resultData.environment,
                hasIssue: !!resultData.issue,
                hasResolution: !!resultData.resolution
            });

            // Use already loaded data if available, otherwise fetch
            const loadArticleDetails = hasLoadedDetails
                ? Promise.resolve(resultData)
                : fetch('/api/kcs-article-details', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        id: resultData.id,
                        url: resultData.url || resultData.view_uri,
                        document_kind: resultData.document_kind,
                        config: {
                            redhat_token: localStorage.getItem('redhat_token') || sessionStorage.getItem('redhat_token')
                        }
                    })
                }).then(response => response.json());

            loadArticleDetails.then(fullArticle => {
                console.log('📋 KCS article details:', hasLoadedDetails ? '(from lazy load)' : '(from API fetch)', fullArticle);

                // Update resultData with publish state from full article if available
                if (fullArticle.publish_state && fullArticle.publish_state !== 'N/A') {
                    resultData.publish_state = fullArticle.publish_state;
                    console.log('✅ Updated publish_state:', fullArticle.publish_state);
                }

                // Determine status based on publish_state from API
                let statusClass = 'status-verified';
                let statusText = 'Published';

                if (fullArticle.publish_state) {
                    const state = fullArticle.publish_state.toLowerCase();
                    if (state === 'unpublished') {
                        statusClass = 'status-draft';
                        statusText = 'Unpublished';
                    } else if (state === 'solution verified') {
                        statusClass = 'status-verified';
                        statusText = 'Solution Verified';
                    } else if (state === 'solution unverified') {
                        statusClass = 'status-pending';
                        statusText = 'Solution Unverified';
                    } else if (state === 'solution in progress') {
                        statusClass = 'status-pending';
                        statusText = 'Solution In Progress';
                    } else if (state !== 'n/a') {
                        statusText = fullArticle.publish_state;
                    }
                }

                // Always show Environment section, use "No environment information" if empty
                const environmentText = (fullArticle.environment && fullArticle.environment.trim() !== '')
                    ? formatKCSContent(fullArticle.environment)
                    : '<em style="color: #999;">No environment information</em>';

                // Update with full article content
                overviewTabContent.innerHTML = `
                    <div class="kcs-sections" style="padding: 1.5rem;">
                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Environment</h4>
                            <div class="kcs-section-text">${environmentText}</div>
                        </div>

                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Status</h4>
                            <div class="kcs-section-text"><span class="kcs-status ${statusClass}">${statusText}</span></div>
                        </div>

                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Issue</h4>
                            <div class="kcs-section-text">${formatKCSContent(fullArticle.issue || resultData.issue || fullArticle.abstract || 'No issue description available')}</div>
                        </div>

                        <div class="kcs-action-buttons" style="display: flex; gap: 0.75rem; margin-top: 1.5rem;">
                            <a href="${articleUrl}" target="_blank" class="view-link">View Full KCS Article</a>
                            <button class="view-link copy-kcs-link-btn" onclick="copyKCSLink(this)" data-url="${articleUrl}">
                                Copy KCS Article Link
                            </button>
                        </div>
                    </div>
                `;
                console.log('✅ KCS: Loaded full article details');
            })
            .catch(error => {
                console.error('❌ Error loading KCS article details:', error);
                // Fallback to basic data with Environment section
                overviewTabContent.innerHTML = `
                    <div class="kcs-sections" style="padding: 1.5rem;">
                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Environment</h4>
                            <div class="kcs-section-text"><em style="color: #999;">No environment information</em></div>
                        </div>

                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Status</h4>
                            <div class="kcs-section-text"><span class="kcs-status ${getVerificationStatus(resultData)}"</span></div>
                        </div>

                        <div class="kcs-section">
                            <h4 class="kcs-section-title">Issue</h4>
                            <div class="kcs-section-text">${formatKCSContent(resultData.issue || resultData.abstract || 'No issue description available')}</div>
                        </div>

                        <div class="kcs-section" style="margin-top: 1rem;">
                            <p style="color: #999;">Unable to load full article details. <a href="${articleUrl}" target="_blank">View full article</a></p>
                        </div>

                        <div class="kcs-action-buttons" style="display: flex; gap: 0.75rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #e0e0e0;">
                            <a href="${articleUrl}" target="_blank" class="view-link">View Full KCS Article</a>
                            <button class="view-link copy-kcs-link-btn" onclick="copyKCSLink(this)" data-url="${articleUrl}">
                                Copy KCS Article Link
                            </button>
                        </div>
                    </div>
                `;
            });
        } else {
            console.error('❌ KCS: Could not find overview tab content');
        }
    } else {
        // For non-KCS sources, restore the standard Overview tab structure if it was replaced
        const overviewTabContent = detailPanel.querySelector('.tab-content[data-tab-content="overview"]');

        // Check if we need to restore the standard structure (if KCS custom HTML exists)
        if (overviewTabContent && !overviewTabContent.querySelector('.section-label')) {
            // Restore standard structure
            overviewTabContent.innerHTML = `
                <div class="detail-section">
                    <h4 class="section-label">Issue Description</h4>
                    <p class="section-text">Loading...</p>
                </div>
            `;
        }

        // Now get the section elements (they should exist after restoration)
        const restoredSectionText = overviewTabContent?.querySelector('.section-text');

        if (restoredSectionText) {
            if (source === 'salesforce') {
                // Show loading state initially
                restoredSectionText.textContent = 'Loading...';

                // Fetch full description from API
                fetch(`/api/sfdc/case/${resultData.case_number}`)
                    .then(response => response.json())
                    .then(details => {
                        // Update description with fetched data
                        restoredSectionText.textContent = details.description || 'No description available';
                    })
                    .catch(error => {
                        console.error('Error loading SFDC case description:', error);
                        restoredSectionText.textContent = resultData.description || 'Error loading description';
                    });

                // Fetch Related Content from SFDC case comments (KCS, Docs, Slack)
                const sfdcCaseNumber = resultData.case_number;
                if (sfdcCaseNumber) {
                    const cacheKey = `sfdc-${sfdcCaseNumber}`;
                    if (relatedContentCache.ohss[cacheKey]) {
                        console.log(`💾 Using cached Related Content for SFDC case ${sfdcCaseNumber}`);
                        const cached = relatedContentCache.ohss[cacheKey];
                        if (cached.kcs_articles && cached.kcs_articles.length > 0) {
                            updateRelatedKCSFromJira(cached.kcs_articles);
                        }
                        if (cached.redhat_docs && cached.redhat_docs.length > 0) {
                            updateRelatedDocsFromJira(cached.redhat_docs);
                        }
                        if (cached.slack_threads && cached.slack_threads.length > 0) {
                            updateRelatedSlackThreads(cached.slack_threads);
                        }
                        if (cached.icm_tickets && cached.icm_tickets.length > 0) {
                            updateRelatedICMTickets(cached.icm_tickets);
                        }
                        if ((!cached.kcs_articles || cached.kcs_articles.length === 0) &&
                            (!cached.redhat_docs || cached.redhat_docs.length === 0) &&
                            (!cached.slack_threads || cached.slack_threads.length === 0) &&
                            (!cached.icm_tickets || cached.icm_tickets.length === 0)) {
                            const relatedItems = detailPanel.querySelector('.related-items');
                            if (relatedItems) {
                                relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">No related content found in case comments</p>';
                            }
                        }
                    } else {
                        console.log(`🔗 Fetching Related Content for SFDC case: ${sfdcCaseNumber}`);
                        fetch(`/api/sfdc/case/${sfdcCaseNumber}/related-content`, {
                            credentials: 'include'
                        })
                            .then(resp => resp.json())
                            .then(data => {
                                console.log('📋 SFDC Related Content received:', data);

                                relatedContentCache.ohss[cacheKey] = {
                                    kcs_articles: data.kcs_articles || [],
                                    redhat_docs: data.redhat_docs || [],
                                    slack_threads: data.slack_threads || [],
                                    icm_tickets: data.icm_tickets || []
                                };

                                if (data.kcs_articles && data.kcs_articles.length > 0) {
                                    updateRelatedKCSFromJira(data.kcs_articles);
                                }
                                if (data.redhat_docs && data.redhat_docs.length > 0) {
                                    updateRelatedDocsFromJira(data.redhat_docs);
                                }
                                if (data.slack_threads && data.slack_threads.length > 0) {
                                    updateRelatedSlackThreads(data.slack_threads);
                                }
                                if (data.icm_tickets && data.icm_tickets.length > 0) {
                                    updateRelatedICMTickets(data.icm_tickets);
                                }
                                if ((!data.kcs_articles || data.kcs_articles.length === 0) &&
                                    (!data.redhat_docs || data.redhat_docs.length === 0) &&
                                    (!data.slack_threads || data.slack_threads.length === 0) &&
                                    (!data.icm_tickets || data.icm_tickets.length === 0)) {
                                    const relatedItems = detailPanel.querySelector('.related-items');
                                    if (relatedItems) {
                                        relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">No related content found in case comments</p>';
                                    }
                                }
                            })
                            .catch(err => {
                                console.error('Error fetching SFDC Related Content:', err);
                                const relatedItems = detailPanel.querySelector('.related-items');
                                if (relatedItems) {
                                    relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">No related content available</p>';
                                }
                            });
                    }
                }
            } else if (source === 'ohss' || source === 'jira') {
                // Format the description with proper line breaks and styling
                const description = resultData.description || 'No description available';
                // Replace newlines with <br> tags for proper formatting
                const formattedDescription = description.replace(/\n/g, '<br>');
                restoredSectionText.innerHTML = formattedDescription;

                // Fetch Related Content for OHSS/Jira tickets from comments
                const jiraKey = resultData.key;
                if (jiraKey) {
                    // Check if already cached
                    if (relatedContentCache.ohss[jiraKey]) {
                        console.log(`💾 Using cached Related Content for ${jiraKey}`);
                        const cachedData = relatedContentCache.ohss[jiraKey];

                        // Update KCS Articles from cache
                        if (cachedData.kcs_articles && Array.isArray(cachedData.kcs_articles) && cachedData.kcs_articles.length > 0) {
                            updateRelatedKCSFromJira(cachedData.kcs_articles);
                        }

                        // Update Red Hat Docs from cache
                        if (cachedData.redhat_docs && Array.isArray(cachedData.redhat_docs) && cachedData.redhat_docs.length > 0) {
                            updateRelatedDocsFromJira(cachedData.redhat_docs);
                        }

                        // Update Slack Threads from cache
                        if (cachedData.slack_threads && Array.isArray(cachedData.slack_threads) && cachedData.slack_threads.length > 0) {
                            updateRelatedSlackThreads(cachedData.slack_threads);
                        }

                        // Update SOP/GitHub Links from cache
                        if (cachedData.github_links && Array.isArray(cachedData.github_links) && cachedData.github_links.length > 0) {
                            updateRelatedSOPLinks(cachedData.github_links);
                        }

                        // Update Linked Salesforce Cases tab from cache
                        renderLinkedSFDCCases(cachedData.cases);

                        // Skip the fetch - we already have the data
                        return;
                    }

                    // Check if request is already in-flight - just skip, don't wait
                    if (inFlightRequests.has(jiraKey)) {
                        console.log(`⏳ Request already in-flight for ${jiraKey}, skipping duplicate`);
                        return;
                    }

                    console.log(`🔗 Fetching Related Content for Jira ticket: ${jiraKey}`);

                    // Create the fetch promise and store it to prevent duplicate requests
                    const fetchPromise = fetch(`/api/jira-issue-links/${jiraKey}`, {
                        method: 'GET',
                        credentials: 'include'
                    })
                        .then(resp => resp.json())
                        .then(jiraData => {
                            console.log('📋 Jira Related Content received:', jiraData);

                            // Cache immediately
                            const cachedData = {
                                kcs_articles: jiraData.kcs_articles || [],
                                redhat_docs: jiraData.redhat_docs || [],
                                slack_threads: jiraData.slack_threads || [],
                                github_links: jiraData.github_links || [],
                                cases: jiraData.cases || []
                            };
                            relatedContentCache.ohss[jiraKey] = cachedData;

                            // Remove from in-flight
                            inFlightRequests.delete(jiraKey);

                            // Update UI
                            if (cachedData.kcs_articles && Array.isArray(cachedData.kcs_articles) && cachedData.kcs_articles.length > 0) {
                                updateRelatedKCSFromJira(cachedData.kcs_articles);
                            }

                            if (cachedData.redhat_docs && Array.isArray(cachedData.redhat_docs) && cachedData.redhat_docs.length > 0) {
                                updateRelatedDocsFromJira(cachedData.redhat_docs);
                            }

                            if (cachedData.slack_threads && Array.isArray(cachedData.slack_threads) && cachedData.slack_threads.length > 0) {
                                updateRelatedSlackThreads(cachedData.slack_threads);
                            }

                            if (cachedData.github_links && Array.isArray(cachedData.github_links) && cachedData.github_links.length > 0) {
                                updateRelatedSOPLinks(cachedData.github_links);
                            }

                            // Update Linked Salesforce Cases tab
                            renderLinkedSFDCCases(cachedData.cases);

                            // If no content found, show message
                            if ((!jiraData.kcs_articles || jiraData.kcs_articles.length === 0) &&
                                (!jiraData.redhat_docs || jiraData.redhat_docs.length === 0) &&
                                (!jiraData.slack_threads || jiraData.slack_threads.length === 0) &&
                                (!jiraData.github_links || jiraData.github_links.length === 0)) {
                                const relatedItems = detailPanel.querySelector('.related-items');
                                if (relatedItems) {
                                    relatedItems.innerHTML = '<p style="color: #666; padding: 1rem;">No related content available</p>';
                                }
                            }

                            return cachedData;
                        })
                        .catch(err => {
                            console.error('Error fetching Jira Related Content:', err);
                            inFlightRequests.delete(jiraKey);
                            const relatedItems = detailPanel.querySelector('.related-items');
                            if (relatedItems) {
                                relatedItems.innerHTML = '<p style="color: #999; padding: 1rem;">Unable to load related content</p>';
                            }
                            throw err; // Re-throw so promise stays rejected
                        });

                    // Store the promise in in-flight map
                    inFlightRequests.set(jiraKey, fetchPromise);
                }
            } else if (source === 'slack') {
                const slackText = resultData.text || 'No message content';
                restoredSectionText.innerHTML = slackText.replace(/\n/g, '<br>');
            } else if (source === 'github' || source === 'gitlab') {
                // For GitHub/GitLab, show repository and file information
                const repoInfo = [];
                if (resultData.repository) repoInfo.push(`Repository: ${resultData.repository}`);
                if (resultData.project_name) repoInfo.push(`Project: ${resultData.project_name}`);
                if (resultData.path) repoInfo.push(`File: ${resultData.path}`);
                if (resultData.filename) repoInfo.push(`File: ${resultData.filename}`);
                if (resultData.language) repoInfo.push(`Language: ${resultData.language}`);
                if (resultData.summary) repoInfo.push(`\n${resultData.summary}`);
                else if (resultData.description) repoInfo.push(`\n${resultData.description}`);

                restoredSectionText.textContent = repoInfo.join('\n') || 'No description available';
            } else {
                restoredSectionText.textContent = resultData.abstract || resultData.description || resultData.summary || 'No content available';
            }
        }
    }

    // Update external trackers or linked tickets based on source
    if (source === 'salesforce' && resultData.case_number) {
        const trackersElement = document.getElementById('detail-external-trackers');
        const sectionLabel = detailPanel.querySelector('.tab-content[data-tab-content="escalation-ohss"] .section-label');

        // Show the section label for Salesforce cases
        if (sectionLabel) {
            sectionLabel.style.display = 'block';
            sectionLabel.textContent = 'External Trackers (JIRA)';
        }

        // Show placeholder - will load when tab is clicked
        if (trackersElement) {
            trackersElement.innerHTML = '<p style="color: #666;">Click the "Linked JIRA ticket" tab to load external trackers</p>';
            trackersElement.dataset.caseNumber = resultData.case_number;
            trackersElement.dataset.source = 'salesforce';
            trackersElement.dataset.loaded = 'false';
        }
    } else if ((source === 'ohss' || source === 'jira') && resultData.key) {
        const trackersElement = document.getElementById('detail-external-trackers');
        const sectionLabel = detailPanel.querySelector('.tab-content[data-tab-content="escalation-ohss"] .section-label');

        if (sectionLabel) {
            sectionLabel.style.display = 'block';
            sectionLabel.textContent = 'Linked Salesforce Cases';
        }

        if (trackersElement) {
            trackersElement.innerHTML = '<p style="color: #666;">Loading linked Salesforce cases...</p>';
            trackersElement.dataset.source = 'ohss';
            trackersElement.dataset.jiraKey = resultData.key;
            trackersElement.dataset.loaded = 'false';
            delete trackersElement.dataset.caseNumber;
        }
    }

    // OLD CODE BELOW - REMOVED (was after return statement, making it unreachable)
    // The fetch now happens in the tab click handler (line ~1810)
    if (false && source === 'salesforce') {
        fetch(`/api/case-escalations/${resultData.case_number}`, {
            credentials: 'include'
        })
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            })
            .then(data => {
                console.log('📋 Tracker data received:', data);
                console.log('📋 data.external_trackers:', data.external_trackers);
                console.log('📋 data.raw_data:', data.raw_data);
                console.log('📋 data.error:', data.error);

                // Check for trackers - try external_trackers first (from backend), then raw_data
                const rawTrackers = data.external_trackers ||
                                  (data.raw_data && data.raw_data.externalTrackers) ||
                                  (data.raw_data && data.raw_data.externalSystem);

                console.log('📋 rawTrackers after parsing:', rawTrackers);

                // Display External Trackers (OHSS)
                if (trackersElement) {
                    if (rawTrackers && Array.isArray(rawTrackers) && rawTrackers.length > 0) {
                        // Format: <OHSS ticketNumber> [OHSS link] - <OHSS ticketTitle> - (<OHSS_status>)
                        const trackersList = rawTrackers.map(tracker => {
                            const ticketNumber = tracker.resourceKey || 'N/A';
                            const ticketURL = tracker.resourceURL || '#';
                            const ticketTitle = tracker.title || 'No description';
                            const ticketStatus = tracker.status || 'Unknown';

                            return `
                                <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: #f8f9fa; border-left: 3px solid #0066cc; border-radius: 4px;">
                                    <a href="${ticketURL}" target="_blank" style="color: #0066cc; text-decoration: none; font-weight: 600; font-size: 0.95rem;">
                                        ${ticketNumber}
                                    </a>
                                    <span style="color: #333; margin-left: 0.5rem;">- ${ticketTitle} - (<span style="color: #666;">${ticketStatus}</span>)</span>
                                </div>
                            `;
                        }).join('');

                        trackersElement.innerHTML = trackersList;
                    } else {
                        trackersElement.innerHTML = '<p style="color: #666;">No external trackers found</p>';
                    }
                }

                // Fetch Related Content from linked OHSS tickets
                // Extract OHSS ticket keys from external trackers
                const ohssTickets = [];
                if (rawTrackers && Array.isArray(rawTrackers)) {
                    rawTrackers.forEach(tracker => {
                        const resourceKey = tracker.resourceKey || '';
                        if (resourceKey.startsWith('OHSS-')) {
                            ohssTickets.push(resourceKey);
                        }
                    });
                }

                // Handle Related Content from either OHSS ticket or SFDC case comments
                if (ohssTickets.length > 0) {
                    // Case has linked OHSS ticket - fetch from OHSS comments
                    const ohssKey = ohssTickets[0];

                    // Check cache first
                    if (relatedContentCache.ohss[ohssKey]) {
                        console.log(`💾 Using cached Related Content for ${ohssKey}`);
                        const cached = relatedContentCache.ohss[ohssKey];

                        if (cached.kcs_articles && cached.kcs_articles.length > 0) {
                            updateRelatedKCSFromJira(cached.kcs_articles);
                        }
                        if (cached.slack_threads && cached.slack_threads.length > 0) {
                            updateRelatedSlackThreads(cached.slack_threads);
                        }
                        if (cached.github_links && cached.github_links.length > 0) {
                            updateRelatedSOPLinks(cached.github_links);
                        }
                    } else {
                        console.log(`🔗 Fetching Related Content from linked OHSS ticket: ${ohssKey}`);

                        fetch(`/api/jira-issue-links/${ohssKey}`, {
                            method: 'GET',
                            credentials: 'include'
                        })
                            .then(resp => resp.json())
                            .then(ohssData => {
                                console.log('📋 OHSS Related Content received:', ohssData);

                                // Cache the data
                                relatedContentCache.ohss[ohssKey] = {
                                    kcs_articles: ohssData.kcs_articles || [],
                                    slack_threads: ohssData.slack_threads || [],
                                    github_links: ohssData.github_links || []
                                };

                                // Update KCS Articles
                                if (ohssData.kcs_articles && Array.isArray(ohssData.kcs_articles) && ohssData.kcs_articles.length > 0) {
                                    updateRelatedKCSFromJira(ohssData.kcs_articles);
                                }

                                // Update Slack Threads
                                if (ohssData.slack_threads && Array.isArray(ohssData.slack_threads) && ohssData.slack_threads.length > 0) {
                                    updateRelatedSlackThreads(ohssData.slack_threads);
                                }

                                // Update SOP/GitHub Links
                                if (ohssData.github_links && Array.isArray(ohssData.github_links) && ohssData.github_links.length > 0) {
                                    updateRelatedSOPLinks(ohssData.github_links);
                                }
                            })
                            .catch(err => {
                                console.error('Error fetching OHSS Related Content:', err);
                            });
                    }
                } else {
                    // No OHSS ticket - use Slack threads and KCS articles from SFDC case comments
                    console.log('📋 No OHSS ticket, using Related Content from SFDC case comments');

                    // Update KCS Articles from SFDC case comments
                    if (data.kcs_articles && Array.isArray(data.kcs_articles) && data.kcs_articles.length > 0) {
                        console.log(`✅ Found ${data.kcs_articles.length} KCS articles in SFDC case comments`);
                        updateRelatedKCSFromJira(data.kcs_articles);
                    }

                    // Update Slack Threads from SFDC case comments
                    if (data.slack_threads && Array.isArray(data.slack_threads) && data.slack_threads.length > 0) {
                        console.log(`✅ Found ${data.slack_threads.length} Slack threads in SFDC case comments`);
                        updateRelatedSlackThreads(data.slack_threads);
                    }

                    // Update ICM Tickets from SFDC case comments
                    if (data.icm_tickets && Array.isArray(data.icm_tickets) && data.icm_tickets.length > 0) {
                        console.log(`✅ Found ${data.icm_tickets.length} ICM tickets in SFDC case comments`);
                        updateRelatedICMTickets(data.icm_tickets);
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching tracker data:', error);
                if (trackersElement) {
                    // Show a cleaner error message
                    trackersElement.innerHTML = `<p style="color: #666;">No external trackers found for this case.</p>`;
                }
            });
    }

    console.log('🔍 Checking Jira condition: source =', source, ', resultData.key =', resultData.key, ', condition met:', ((source === 'ohss' || source === 'jira') && resultData.key));

    // ALWAYS try to fetch for Jira tickets (simplified check)
    if ((source === 'ohss' || source === 'jira') && resultData.key) {
        // Fetch linked Salesforce tickets for Jira tickets
        console.log('✅ Jira/OHSS ticket detected, fetching linked SFDC cases for:', resultData.key);

        const trackersElement = document.getElementById('detail-external-trackers');
        console.log('📍 Trackers element found:', !!trackersElement);

        // Update the section label for OHSS tickets
        const sectionLabels = detailPanel.querySelectorAll('.detail-section .section-label');
        sectionLabels.forEach(label => {
            if (label.textContent.includes('External Trackers')) {
                label.textContent = 'External Trackers (Salesforce)';
            }
        });

        // Show loading state
        if (trackersElement) {
            trackersElement.innerHTML = '<p style="color: #666;">Loading linked Salesforce tickets...</p>';
        } else {
            console.error('❌ Trackers element not found!');
        }

        // Search for Salesforce cases that link to this Jira ticket
        const jiraKey = resultData.key;
        console.log('🔑 Jira Key:', jiraKey);

        console.log('🌐 Fetching:', `/api/jira-issue-links/${jiraKey}`);

        // Check cache first
        if (relatedContentCache.ohss[jiraKey]) {
            console.log(`💾 Using cached data for ${jiraKey}`);
            const cached = relatedContentCache.ohss[jiraKey];

            // Update Slack threads
            if (cached.slack_threads && cached.slack_threads.length > 0) {
                window.jiraSlackThreads = cached.slack_threads;
                updateRelatedSlackThreads(cached.slack_threads);
            } else {
                window.jiraSlackThreads = [];
                updateRelatedSlackThreads([]);
            }

            // Update KCS articles
            if (cached.kcs_articles && cached.kcs_articles.length > 0) {
                window.jiraKcsArticles = cached.kcs_articles;
                updateRelatedKCSFromJira(cached.kcs_articles);
            } else {
                window.jiraKcsArticles = [];
            }

            // Update SOP/GitHub links
            if (cached.github_links && cached.github_links.length > 0) {
                updateRelatedSOPLinks(cached.github_links);
            }

            // Use cached cases data (no need to re-fetch)
            if (trackersElement) {
                const linkedCases = cached.cases || [];
                if (linkedCases.length > 0) {
                    trackersElement.innerHTML = linkedCases.map(sfCase => {
                        const caseNumber = sfCase.case_number || 'Unknown';
                        const problemStatement = sfCase.problem_statement || sfCase.summary || 'No problem statement';
                        const status = sfCase.status || 'Unknown';
                        const classicUrl = sfCase.urls?.classic || `https://gss.my.salesforce.com/${sfCase.salesforce_id || ''}`;
                        const portalUrl = sfCase.urls?.customer_portal || sfCase.url || `https://access.redhat.com/support/cases/#/case/${caseNumber}`;

                        return `<div style="margin-bottom: 8px;">${caseNumber} - ${problemStatement} - (${status}) - <a href="${classicUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">SFDC</a> | <a href="${portalUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">Customer Portal</a></div>`;
                    }).join('');
                } else {
                    trackersElement.innerHTML = '<p style="color: #666;">No linked Salesforce tickets found</p>';
                }
            }
        } else {
            // Fetch from API
            fetch(`/api/jira-issue-links/${jiraKey}`, {
                method: 'GET',
                credentials: 'include'
            })
                .then(response => {
                    console.log('📡 Response status:', response.status, response.statusText);
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    return response.json();
                })
                .then(data => {
                    console.log('📋 Linked SFDC tickets response:', data);
                    console.log('📋 SFDC cases found:', data.cases?.length || 0);

                    // Cache the Related Content data including cases
                    relatedContentCache.ohss[jiraKey] = {
                        kcs_articles: data.kcs_articles || [],
                        slack_threads: data.slack_threads || [],
                        github_links: data.github_links || [],
                        cases: data.cases || []
                    };

                    if (trackersElement) {
                        const linkedCases = data.cases || [];

                        if (linkedCases.length > 0) {
                            console.log('📋 First case:', linkedCases[0]);
                        }

                        if (linkedCases.length > 0) {
                            trackersElement.innerHTML = linkedCases.map(sfCase => {
                                const caseNumber = sfCase.case_number || 'Unknown';
                                const problemStatement = sfCase.problem_statement || sfCase.summary || 'No problem statement';
                                const status = sfCase.status || 'Unknown';
                                const classicUrl = sfCase.urls?.classic || `https://gss.my.salesforce.com/${sfCase.salesforce_id || ''}`;
                                const portalUrl = sfCase.urls?.customer_portal || sfCase.url || `https://access.redhat.com/support/cases/#/case/${caseNumber}`;

                                return `<div style="margin-bottom: 8px;">${caseNumber} - ${problemStatement} - (${status}) - <a href="${classicUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">SFDC</a> | <a href="${portalUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">Customer Portal</a></div>`;
                            }).join('');
                        } else {
                            // Show debug info if available
                            const debug = data.debug || {};
                            console.log('🔍 Debug info:', debug);

                            let debugHtml = '<p style="color: #666;">No linked Salesforce tickets found</p>';
                            if (debug.jira_credentials_provided === false) {
                                debugHtml += '<p style="color: #ff9800; font-size: 12px; margin-top: 8px;">⚠️ Jira credentials not configured - cannot check remote links</p>';
                            }
                            if (debug.approaches_attempted) {
                                debugHtml += `<p style="color: #999; font-size: 11px; margin-top: 8px;">Checked: ${debug.approaches_attempted.join(', ')}</p>`;
                            }

                            trackersElement.innerHTML = debugHtml;
                        }
                    }

                    // Handle Slack threads from JIRA comments
                    console.log('🔍 JIRA API response data:', data);
                    console.log('🔍 slack_threads field:', data.slack_threads);
                    if (data.slack_threads && Array.isArray(data.slack_threads) && data.slack_threads.length > 0) {
                        console.log('✅ Slack threads found in JIRA comments:', data.slack_threads.length, data.slack_threads);
                        window.jiraSlackThreads = data.slack_threads;
                        updateRelatedSlackThreads(data.slack_threads);
                    } else {
                        console.log('❌ No Slack threads found in JIRA comments (or field missing)');
                        window.jiraSlackThreads = [];
                        updateRelatedSlackThreads([]);
                    }

                    // Handle KCS articles from JIRA comments
                    console.log('🔍 kcs_articles field:', data.kcs_articles);
                    if (data.kcs_articles && Array.isArray(data.kcs_articles) && data.kcs_articles.length > 0) {
                        console.log('✅ KCS articles found in JIRA comments:', data.kcs_articles.length, data.kcs_articles);
                        window.jiraKcsArticles = data.kcs_articles;
                        updateRelatedKCSFromJira(data.kcs_articles);
                    } else {
                        console.log('❌ No KCS articles found in JIRA comments (or field missing)');
                        window.jiraKcsArticles = [];
                    }

                    // Handle SOP/GitHub links from JIRA comments
                    if (data.github_links && Array.isArray(data.github_links) && data.github_links.length > 0) {
                        console.log('✅ GitHub links found in JIRA comments:', data.github_links.length);
                        updateRelatedSOPLinks(data.github_links);
                    }

                })
                .catch(error => {
                    console.error('Error fetching linked SFDC tickets:', error);
                    if (trackersElement) {
                        trackersElement.innerHTML = `
                            <p style="color: #d32f2f;">Unable to load linked Salesforce tickets</p>
                            <p style="color: #999; font-size: 12px; margin-top: 8px;">Error: ${error.message}</p>
                            <p style="color: #999; font-size: 11px;">Check browser console for details</p>
                        `;
                    }
                });
        }
    }

    // Ensure Overview tab is active by default
    const overviewTab = detailPanel.querySelector('.detail-tab[data-tab="overview"]');
    const overviewContent = detailPanel.querySelector('.tab-content[data-tab-content="overview"]');
    const ohssTabContent = detailPanel.querySelector('.tab-content[data-tab-content="escalation-ohss"]');

    console.log('🔍 Tab debugging:');
    console.log('  Overview tab:', overviewTab);
    console.log('  Overview content:', overviewContent);
    console.log('  OHSS content:', ohssTabContent);

    if (overviewTab && overviewContent) {
        // Remove active from all tabs
        detailPanel.querySelectorAll('.detail-tab').forEach(tab => tab.classList.remove('active'));
        detailPanel.querySelectorAll('.tab-content').forEach(content => {
            console.log('  Removing active from:', content.getAttribute('data-tab-content'));
            content.classList.remove('active');
        });

        // Activate Overview tab ONLY
        overviewTab.classList.add('active');
        overviewContent.classList.add('active');

        // Explicitly ensure OHSS tab is NOT active
        if (ohssTabContent) {
            ohssTabContent.classList.remove('active');
        }

        console.log('✅ Final state:');
        console.log('  Overview active?', overviewContent.classList.contains('active'));
        console.log('  OHSS active?', ohssTabContent?.classList.contains('active'));
    }

    console.log(`📋 Detail panel opened for ${source}:`, resultData);
}

// Update Related Content KCS Articles from case
function updateRelatedKCSArticles(kcsArticles) {
    const kcsTab = document.querySelector('.related-tab:first-child');

    if (kcsTab) {
        kcsTab.textContent = `KCS Articles (${kcsArticles.length})`;
        kcsTab.setAttribute('data-content', 'kcs');
    }

    // Store for tab switching
    window.relatedKCSContent = kcsArticles;

    // Show KCS articles if this tab is active
    const relatedItemsContainer = document.querySelector('.related-items');
    if (kcsTab && kcsTab.classList.contains('active') && relatedItemsContainer) {
        if (kcsArticles.length > 0) {
            relatedItemsContainer.innerHTML = kcsArticles.map(article => `
                <a href="${article.url}" target="_blank" class="related-item">
                    <img src="/src/images/Logo-Red_Hat-Hat_icon-Red-RGB.svg" class="related-icon" alt="KCS" />
                    <div class="related-info">
                        <div class="related-title">${article.title}</div>
                        <div class="related-subtitle">${article.abstract || `Article ${article.solution_id}`}</div>
                    </div>
                </a>
            `).join('');
        } else {
            relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No KCS articles linked to this case</p>';
        }
    }
}

// Populate the "Linked Salesforce ticket" tab for OHSS/Jira results
function renderLinkedSFDCCases(cases) {
    const trackersElement = document.getElementById('detail-external-trackers');
    const detailPanel = document.getElementById('detail-panel');
    const sectionLabel = detailPanel ? detailPanel.querySelector('.tab-content[data-tab-content="escalation-ohss"] .section-label') : null;

    if (sectionLabel) {
        sectionLabel.style.display = 'block';
        sectionLabel.textContent = 'Linked Salesforce Cases';
    }

    if (!trackersElement) return;

    if (cases && Array.isArray(cases) && cases.length > 0) {
        trackersElement.innerHTML = cases.map(sfCase => {
            const caseNumber = sfCase.case_number || 'Unknown';
            const problemStatement = sfCase.problem_statement || sfCase.summary || 'No problem statement';
            const status = sfCase.status || 'Unknown';
            const classicUrl = sfCase.urls?.classic || `https://gss.my.salesforce.com/${sfCase.salesforce_id || ''}`;
            const portalUrl = sfCase.urls?.customer_portal || sfCase.url || `https://access.redhat.com/support/cases/#/case/${caseNumber}`;

            return `<div style="margin-bottom: 8px;">${caseNumber} - ${problemStatement} - (${status}) - <a href="${classicUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">SFDC</a> | <a href="${portalUrl}" target="_blank" style="color: #0052CC; text-decoration: none;">Customer Portal</a></div>`;
        }).join('');
    } else {
        trackersElement.innerHTML = '<p style="color: #666;">No linked Salesforce cases found</p>';
    }
    trackersElement.dataset.loaded = 'true';
}

// Helper functions to extract Slack info from URLs
function extractChannelFromSlackUrl(url) {
    const match = url.match(/archives\/([A-Z0-9]+)/);
    return match ? match[1] : 'Unknown';
}

function extractTimestampFromSlackUrl(url) {
    const match = url.match(/p(\d+)/);
    return match ? match[1] : '';
}

// Update Related Content for OHSS tickets with dynamic tabs
function updateOHSSRelatedContent(slackThreads, kcsArticles, redhatDocs) {
    const relatedTabs = document.querySelector('.related-tabs');
    const relatedItems = document.querySelector('.related-items');
    if (!relatedTabs) return;

    // Clear existing tabs and items
    relatedTabs.innerHTML = '';
    if (relatedItems) relatedItems.innerHTML = '';

    // Add KCS Articles tab if there are articles
    if (kcsArticles && kcsArticles.length > 0) {
        const kcsTab = document.createElement('button');
        kcsTab.className = 'related-tab kcs-tab active';
        kcsTab.textContent = `KCS Articles (${kcsArticles.length})`;
        kcsTab.setAttribute('data-content', 'kcs');
        relatedTabs.appendChild(kcsTab);

        // Store KCS content and fetch titles asynchronously
        window.relatedKCSContent = kcsArticles.map(url => {
            const articleId = url.match(/\/(solutions|articles)\/(\d+)/);
            const type = articleId ? articleId[1] : 'solutions';
            const id = articleId ? articleId[2] : 'Unknown';
            const typeLabel = type === 'solutions' ? 'Solution' : 'Article';

            const article = {
                id: id,
                solution_id: id,
                title: `KCS ${typeLabel} ${id}`,
                abstract: `Loading...`,
                url: url,
                type: type
            };

            // Fetch actual title from KCS API
            fetch(`https://access.redhat.com/hydra/rest/search/kcs/solutions/${id}`, {
                credentials: 'include'
            })
            .then(r => r.json())
            .then(data => {
                if (data && data.title) {
                    article.title = data.title;
                    article.abstract = data.abstract || 'Linked from ticket comments';
                    // Refresh the display if KCS tab is currently active
                    const activeTab = document.querySelector('.related-tab.active');
                    if (activeTab && activeTab.getAttribute('data-content') === 'kcs') {
                        activeTab.click(); // Re-render
                    }
                }
            })
            .catch(() => {
                article.abstract = 'Linked from ticket comments';
            });

            return article;
        });
    }

    // Add Red Hat Documentation tab if there are docs
    if (redhatDocs && redhatDocs.length > 0) {
        const docsTab = document.createElement('button');
        docsTab.className = 'related-tab docs-tab';
        if (relatedTabs.children.length === 0) docsTab.classList.add('active');
        docsTab.textContent = `Red Hat Docs (${redhatDocs.length})`;
        docsTab.setAttribute('data-content', 'docs');
        relatedTabs.appendChild(docsTab);

        // Store docs content
        window.relatedDocsContent = redhatDocs.map(url => {
            const title = url.split('/').pop().replace(/-/g, ' ');
            return {
                title: title,
                url: url
            };
        });
    }

    // Add Slack Threads tab if there are threads
    if (slackThreads && slackThreads.length > 0) {
        const slackTab = document.createElement('button');
        slackTab.className = 'related-tab slack-tab';
        if (relatedTabs.children.length === 0) slackTab.classList.add('active');
        slackTab.textContent = `Slack Threads (${slackThreads.length})`;
        slackTab.setAttribute('data-content', 'slack');
        relatedTabs.appendChild(slackTab);

        // Store Slack content
        window.relatedSlackContent = slackThreads.map(url => ({
            url: url,
            channel: extractChannelFromSlackUrl(url),
            timestamp: extractTimestampFromSlackUrl(url)
        }));
    }

    // If no content, show message
    if (relatedTabs.children.length === 0) {
        relatedTabs.innerHTML = '<p style="padding: 1rem; color: #666;">No related content found</p>';
    } else {
        // Attach click handlers to newly created tabs
        const relatedItemsContainer = document.querySelector('.related-items');
        relatedTabs.querySelectorAll('.related-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                // Remove active class from all tabs
                relatedTabs.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Show content based on which tab was clicked
                const contentType = tab.getAttribute('data-content');

                if (contentType === 'kcs' && window.relatedKCSContent) {
                    const kcsArticles = window.relatedKCSContent;
                    if (kcsArticles.length > 0) {
                        relatedItemsContainer.innerHTML = kcsArticles.map(article => `
                            <a href="${article.url}" target="_blank" class="related-item">
                                <img src="/src/images/Logo-Red_Hat-Hat_icon-Red-RGB.svg" class="related-icon" alt="KCS" />
                                <div class="related-info">
                                    <div class="related-title">${article.title}</div>
                                    <div class="related-subtitle">${article.abstract || 'Linked from ticket comments'}</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No KCS articles found</p>';
                    }
                } else if (contentType === 'docs' && window.relatedDocsContent) {
                    const docs = window.relatedDocsContent;
                    if (docs.length > 0) {
                        relatedItemsContainer.innerHTML = docs.map(doc => `
                            <a href="${doc.url}" target="_blank" class="related-item">
                                <svg class="related-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                </svg>
                                <div class="related-info">
                                    <div class="related-title">${doc.title}</div>
                                    <div class="related-subtitle">Red Hat Documentation</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No documentation found</p>';
                    }
                } else if (contentType === 'slack' && window.relatedSlackContent) {
                    const slackThreads = window.relatedSlackContent;
                    if (slackThreads.length > 0) {
                        relatedItemsContainer.innerHTML = slackThreads.map(thread => `
                            <a href="${thread.url}" target="_blank" class="related-item">
                                <svg class="related-icon" viewBox="0 0 24 24" width="32" height="32" fill="none">
                                    <path fill="#E01E5A" d="M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52z"/>
                                    <path fill="#36C5F0" d="M6.313 15.165a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313z"/>
                                    <path fill="#2EB67D" d="M8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.527 2.527 0 012.521 2.522v2.52h-2.521z"/>
                                    <path fill="#ECB22E" d="M8.834 6.313a2.527 2.527 0 012.521 2.521 2.527 2.527 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312z"/>
                                </svg>
                                <div class="related-info">
                                    <div class="related-title">Slack thread in #${thread.channel_name || thread.channel || 'unknown'}</div>
                                    <div class="related-subtitle">Thread from ticket comments</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No Slack threads found</p>';
                    }
                }
            });
        });

        // Trigger display of the first active tab
        const firstTab = relatedTabs.querySelector('.related-tab.active');
        if (firstTab) {
            firstTab.click();
        }
    }
}

// Update Related Content KCS Articles from JIRA
function updateRelatedKCSFromJira(kcsArticles) {
    const relatedTabs = document.querySelector('.related-tabs');
    if (!relatedTabs) return;

    // Look for existing KCS tab
    let kcsTab = document.querySelector('.related-tab[data-content="kcs"]');

    if (!kcsTab && kcsArticles.length > 0) {
        // Create KCS tab if it doesn't exist
        kcsTab = document.createElement('button');
        kcsTab.className = 'related-tab kcs-tab';
        kcsTab.setAttribute('data-content', 'kcs');

        // Insert as first tab
        if (relatedTabs.firstChild) {
            relatedTabs.insertBefore(kcsTab, relatedTabs.firstChild);
        } else {
            relatedTabs.appendChild(kcsTab);
        }

        // If this is the only tab, make it active
        if (relatedTabs.children.length === 1) {
            kcsTab.classList.add('active');
        }
    }

    if (kcsTab) {
        kcsTab.textContent = `KCS Articles (${kcsArticles.length})`;

        // Add click handler if not already added
        if (!kcsTab.dataset.listenerAdded) {
            kcsTab.addEventListener('click', () => {
                // Remove active class from all tabs
                document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                kcsTab.classList.add('active');

                // Show KCS content
                const relatedItemsContainer = document.querySelector('.related-items');
                if (relatedItemsContainer) {
                    if (kcsArticles.length > 0) {
                        relatedItemsContainer.innerHTML = kcsArticles.map(article => `
                            <a href="${article.url}" target="_blank" class="related-item">
                                <img src="/src/images/Logo-Red_Hat-Hat_icon-Red-RGB.svg" class="related-icon" alt="KCS" />
                                <div class="related-info">
                                    <div class="related-title">${article.title}</div>
                                    <div class="related-subtitle">Linked from ticket comments</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No KCS articles found</p>';
                    }
                }
            });
            kcsTab.dataset.listenerAdded = 'true';
        }
    }

    // Store for later
    window.relatedKCSContent = kcsArticles;

    // If this tab is active, render content now
    if (kcsTab && kcsTab.classList.contains('active')) {
        kcsTab.click();
    }
}

// Update Related Content Slack Threads from case
function updateRelatedSlackThreads(slackThreads) {
    const relatedTabs = document.querySelector('.related-tabs');
    if (!relatedTabs) return;

    // Look for existing Slack tab
    let slackTab = document.querySelector('.related-tab[data-content="slack"]');

    if (!slackTab && slackThreads.length > 0) {
        // Create Slack tab if it doesn't exist
        slackTab = document.createElement('button');
        slackTab.className = 'related-tab';
        slackTab.setAttribute('data-content', 'slack');
        relatedTabs.appendChild(slackTab);

        // If this is the only tab, make it active
        if (relatedTabs.children.length === 1) {
            slackTab.classList.add('active');
        }
    }

    if (slackTab) {
        slackTab.textContent = `Slack Threads (${slackThreads.length})`;

        // Add click handler if not already added
        if (!slackTab.dataset.listenerAdded) {
            slackTab.addEventListener('click', () => {
                // Remove active class from all tabs
                document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                slackTab.classList.add('active');

                // Show Slack content
                const relatedItemsContainer = document.querySelector('.related-items');
                if (relatedItemsContainer) {
                    if (slackThreads.length > 0) {
                        relatedItemsContainer.innerHTML = slackThreads.map(thread => {
                            const channelName = thread.channel_name || thread.channel_id || 'unknown';
                            const displayTitle = thread.title || `Slack thread in #${channelName}`;

                            return `
                                <a href="${thread.url}" target="_blank" class="related-item">
                                    <img src="/src/images/slack_logo_icon.svg" class="related-icon" alt="Slack" />
                                    <div class="related-info">
                                        <div class="related-title">${displayTitle}</div>
                                        <div class="related-subtitle">${thread.visibility || 'Thread from ticket comments'}</div>
                                    </div>
                                </a>
                            `;
                        }).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No Slack threads linked to this case</p>';
                    }
                }
            });
            slackTab.dataset.listenerAdded = 'true';
        }
    }

    // Store for later
    window.relatedSlackContent = slackThreads;

    // If this tab is active, render content now
    if (slackTab && slackTab.classList.contains('active')) {
        slackTab.click();
    }
}

// Update Related Content Red Hat Docs from Jira
function updateRelatedDocsFromJira(redhatDocs) {
    const relatedTabs = document.querySelector('.related-tabs');
    if (!relatedTabs) return;

    // Look for existing Docs tab
    let docsTab = document.querySelector('.related-tab[data-content="docs"]');

    if (!docsTab && redhatDocs.length > 0) {
        // Create Docs tab if it doesn't exist
        docsTab = document.createElement('button');
        docsTab.className = 'related-tab';
        docsTab.setAttribute('data-content', 'docs');

        // Insert after KCS tab if it exists, otherwise insert first
        const kcsTab = document.querySelector('.related-tab[data-content="kcs"]');
        if (kcsTab && kcsTab.nextSibling) {
            relatedTabs.insertBefore(docsTab, kcsTab.nextSibling);
        } else if (kcsTab) {
            relatedTabs.appendChild(docsTab);
        } else if (relatedTabs.firstChild) {
            relatedTabs.insertBefore(docsTab, relatedTabs.firstChild);
        } else {
            relatedTabs.appendChild(docsTab);
        }

        // If this is the only tab, make it active
        if (relatedTabs.children.length === 1) {
            docsTab.classList.add('active');
        }
    }

    if (docsTab) {
        docsTab.textContent = `Documentation (${redhatDocs.length})`;

        // Add click handler if not already added
        if (!docsTab.dataset.listenerAdded) {
            docsTab.addEventListener('click', () => {
                // Remove active class from all tabs
                document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                docsTab.classList.add('active');

                // Show Docs content
                const relatedItemsContainer = document.querySelector('.related-items');
                if (relatedItemsContainer) {
                    if (redhatDocs.length > 0) {
                        relatedItemsContainer.innerHTML = redhatDocs.map(doc => `
                            <a href="${doc.url}" target="_blank" class="related-item">
                                <img src="/src/images/Logo-Red_Hat-Hat_icon-Red-RGB.svg" class="related-icon" alt="Docs" />
                                <div class="related-info">
                                    <div class="related-title">${doc.title}</div>
                                    <div class="related-subtitle">Linked from ticket comments</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No documentation links found</p>';
                    }
                }
            });
            docsTab.dataset.listenerAdded = 'true';
        }
    }

    // Store for later
    window.relatedDocsContent = redhatDocs;

    // If this tab is active, render content now
    if (docsTab && docsTab.classList.contains('active')) {
        docsTab.click();
    }
}

// Update Related Content SOP/GitHub Links from Jira comments
function updateRelatedSOPLinks(githubLinks) {
    const relatedTabs = document.querySelector('.related-tabs');
    if (!relatedTabs) return;

    let sopTab = document.querySelector('.related-tab[data-content="sop"]');

    if (!sopTab && githubLinks.length > 0) {
        sopTab = document.createElement('button');
        sopTab.className = 'related-tab';
        sopTab.setAttribute('data-content', 'sop');
        relatedTabs.appendChild(sopTab);

        if (relatedTabs.children.length === 1) {
            sopTab.classList.add('active');
        }
    }

    if (sopTab) {
        sopTab.textContent = `SOP (${githubLinks.length})`;

        if (!sopTab.dataset.listenerAdded) {
            sopTab.addEventListener('click', () => {
                document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                sopTab.classList.add('active');

                const relatedItemsContainer = document.querySelector('.related-items');
                if (relatedItemsContainer) {
                    if (githubLinks.length > 0) {
                        relatedItemsContainer.innerHTML = githubLinks.map(link => `
                            <a href="${link.url}" target="_blank" class="related-item">
                                <img src="/src/images/github_logo_icon.svg" class="related-icon" alt="GitHub" />
                                <div class="related-info">
                                    <div class="related-title">${link.title}</div>
                                    <div class="related-subtitle">Linked from ticket comments</div>
                                </div>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No SOP links found</p>';
                    }
                }
            });
            sopTab.dataset.listenerAdded = 'true';
        }
    }

    window.relatedSOPContent = githubLinks;

    if (sopTab && sopTab.classList.contains('active')) {
        sopTab.click();
    }
}

// Update Related Content ICM Tickets
function updateRelatedICMTickets(icmTickets) {
    const relatedTabs = document.querySelector('.related-tabs');
    if (!relatedTabs) return;

    let icmTab = document.querySelector('.related-tab[data-content="icm"]');

    if (!icmTab && icmTickets.length > 0) {
        icmTab = document.createElement('button');
        icmTab.className = 'related-tab';
        icmTab.setAttribute('data-content', 'icm');
        relatedTabs.appendChild(icmTab);

        if (relatedTabs.children.length === 1) {
            icmTab.classList.add('active');
        }
    }

    if (icmTab) {
        icmTab.textContent = `ICM Tickets (${icmTickets.length})`;

        if (!icmTab.dataset.listenerAdded) {
            icmTab.addEventListener('click', () => {
                document.querySelectorAll('.related-tab').forEach(t => t.classList.remove('active'));
                icmTab.classList.add('active');

                const relatedItemsContainer = document.querySelector('.related-items');
                if (relatedItemsContainer) {
                    if (icmTickets.length > 0) {
                        relatedItemsContainer.innerHTML = icmTickets.map(ticket => `
                            <a href="${ticket.url}" target="_blank" class="related-item">
                                <img src="/src/images/icm-logo.png" class="related-icon" alt="ICM" />
                                <div class="related-info">
                                    <div class="related-title">${ticket.title}</div>
                                    <div class="related-subtitle">Microsoft ICM Portal</div>
                                </div>
                                <svg class="external-link" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M12 2h2v2M14 2L8 8M6 3H4a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-2"/>
                                </svg>
                            </a>
                        `).join('');
                    } else {
                        relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No ICM tickets found</p>';
                    }
                }
            });
            icmTab.dataset.listenerAdded = 'true';
        }
    }

    window.relatedICMContent = icmTickets;

    if (icmTab && icmTab.classList.contains('active')) {
        icmTab.click();
    }
}

// Initialize Related Content tab switching
function initRelatedContentTabs() {
    const relatedTabs = document.querySelectorAll('.related-tab');
    const relatedItemsContainer = document.querySelector('.related-items');

    relatedTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active class from all tabs
            relatedTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Show content based on which tab was clicked
            const contentType = tab.getAttribute('data-content');

            if (contentType === 'kcs' && window.relatedKCSContent) {
                const kcsArticles = window.relatedKCSContent;
                if (kcsArticles.length > 0) {
                    relatedItemsContainer.innerHTML = kcsArticles.map(article => `
                        <a href="${article.url}" target="_blank" class="related-item">
                            <img src="/src/images/Logo-Red_Hat-Hat_icon-Red-RGB.svg" class="related-icon" alt="KCS" />
                            <div class="related-info">
                                <div class="related-title">${article.title}</div>
                                <div class="related-subtitle">${article.abstract || `Article ${article.solution_id}`}</div>
                            </div>
                        </a>
                    `).join('');
                } else {
                    relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No KCS articles linked to this case</p>';
                }
            } else if (contentType === 'docs' && window.relatedDocsContent) {
                const docs = window.relatedDocsContent;
                if (docs.length > 0) {
                    relatedItemsContainer.innerHTML = docs.map(doc => `
                        <a href="${doc.url}" target="_blank" class="related-item">
                            <svg class="related-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                            </svg>
                            <div class="related-info">
                                <div class="related-title">${doc.title}</div>
                                <div class="related-subtitle">Red Hat Documentation</div>
                            </div>
                        </a>
                    `).join('');
                } else {
                    relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No documentation links found</p>';
                }
            } else if (contentType === 'slack' && window.relatedSlackContent) {
                const slackThreads = window.relatedSlackContent;
                if (slackThreads.length > 0) {
                    relatedItemsContainer.innerHTML = slackThreads.map(thread => {
                        const channelName = thread.channel_name || thread.channel_id || 'unknown';
                        const displayTitle = thread.title || `Slack thread in #${channelName}`;

                        return `
                        <a href="${thread.url}" target="_blank" class="related-item">
                            <svg class="related-icon" viewBox="0 0 24 24" width="32" height="32" fill="none">
                                <path fill="#E01E5A" d="M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52z"/>
                                <path fill="#36C5F0" d="M6.313 15.165a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313z"/>
                                <path fill="#2EB67D" d="M8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.527 2.527 0 012.521 2.522v2.52h-2.521z"/>
                                <path fill="#ECB22E" d="M8.834 6.313a2.527 2.527 0 012.521 2.521 2.527 2.527 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312z"/>
                            </svg>
                            <div class="related-info">
                                <div class="related-title">${displayTitle}</div>
                                <div class="related-subtitle">Thread from ticket comments</div>
                            </div>
                        </a>
                        `;
                    }).join('');
                } else {
                    relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No Slack threads found in ticket comments</p>';
                }
            } else if (contentType === 'sop' && window.relatedSOPContent) {
                const githubLinks = window.relatedSOPContent;
                if (githubLinks.length > 0) {
                    relatedItemsContainer.innerHTML = githubLinks.map(link => `
                        <a href="${link.url}" target="_blank" class="related-item">
                            <img src="/src/images/github_logo_icon.svg" class="related-icon" alt="GitHub" />
                            <div class="related-info">
                                <div class="related-title">${link.title}</div>
                                <div class="related-subtitle">Linked from ticket comments</div>
                            </div>
                        </a>
                    `).join('');
                } else {
                    relatedItemsContainer.innerHTML = '<p style="color: #666; padding: 16px;">No SOP links found in ticket comments</p>';
                }
            }
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initRelatedContentTabs);

// Tab switching functionality
function initDetailTabs() {
    // Use the global detailPanel variable (declared at line 1860)
    if (!detailPanel) return;

    const tabs = detailPanel.querySelectorAll('.detail-tab');
    const tabContents = detailPanel.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.getAttribute('data-tab');

            // Remove active class from all tabs and contents
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Add active class to clicked tab
            tab.classList.add('active');

            // Show corresponding content
            const targetContent = detailPanel.querySelector(`[data-tab-content="${targetTab}"]`);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
}

// Add click listeners to all result items after they're rendered
function addResultClickListeners() {
    // Remove old delegated listener if it exists
    if (window.resultClickHandler) {
        document.removeEventListener('click', window.resultClickHandler);
    }

    // Use event delegation to handle clicks on dynamically added elements
    window.resultClickHandler = function(e) {
        console.log('🔔 Click detected on:', e.target);
        const resultItem = e.target.closest('.result-item');
        if (!resultItem) {
            console.log('⚠️ Not a result-item');
            return;
        }
        console.log('✅ Found result-item:', resultItem);

        // Don't trigger if clicking on a link
        if (e.target.tagName === 'A' || e.target.closest('a')) return;

        // For Slack messages: toggle expand/collapse inline instead of opening detail panel
        if (resultItem.classList.contains('slack-message')) {
            // Skip if clicking on action buttons
            if (e.target.closest('.view-thread-btn') || e.target.closest('.slack-open-link') || e.target.closest('.slack-toggle-btn')) {
                return;
            }
            // Toggle the expand/collapse on the card
            const msgId = resultItem.getAttribute('data-msg-id');
            const toggleBtn = resultItem.querySelector('.slack-toggle-btn');
            if (msgId && toggleBtn) {
                toggleBtn.click();
            }
            return;
        }

        // Find which section this result belongs to
        const section = resultItem.closest('[data-source]');
        if (!section) return;

        const source = section.getAttribute('data-source');

        console.log('🖱️ Clicked result source:', source);

        // Get the data based on source
        let resultData = null;
        let sourceType = null;

        if (source === 'salesforce') {
            // Use case number to find the correct case (pagination-safe)
            const caseNumber = resultItem.getAttribute('data-case-number');
            console.log('📋 SFDC Click - Case Number from attribute:', caseNumber);
            console.log('📋 Available cases:', window.lastSearchResults?.sfdc?.cases?.length || 0);

            if (caseNumber && window.lastSearchResults?.sfdc?.cases) {
                resultData = window.lastSearchResults.sfdc.cases.find(c => c.case_number === caseNumber);
                console.log('🔍 Looking for case:', caseNumber, 'Found:', resultData ? 'Yes' : 'No');
                if (resultData) {
                    console.log('✅ Case data:', resultData);
                } else {
                    console.error('❌ Case not found in results array');
                    console.log('Available case numbers:', window.lastSearchResults.sfdc.cases.map(c => c.case_number));
                }
            } else {
                console.error('❌ Missing case number or search results');
            }
            sourceType = 'salesforce';
        } else {
            // For other sources, use stable data-attribute lookup (pagination-safe)
            if (source === 'ohss') {
                // Use data-jira-key — immune to pagination offset
                const jiraKey = resultItem.getAttribute('data-jira-key');
                resultData = jiraKey
                    ? window.lastSearchResults?.jira?.issues?.find(i => i.key === jiraKey)
                    : null;
                sourceType = 'jira';
            } else if (source === 'slack') {
                // Use channel-id + thread-ts as composite key
                const channelId = resultItem.getAttribute('data-channel-id');
                const threadTs  = resultItem.getAttribute('data-thread-ts');
                resultData = (channelId && threadTs)
                    ? window.lastSearchResults?.slack?.messages?.find(
                        m => (m.channel_id || m.channel) === channelId && (m.thread_ts || m.ts) === threadTs)
                    : null;
                sourceType = 'slack';
            } else if (source === 'kcs') {
                // Use data-kcs-id
                const kcsId = resultItem.getAttribute('data-kcs-id');
                resultData = kcsId
                    ? window.lastSearchResults?.kcs?.articles?.find(a => (a.id || a.documentKind) === kcsId)
                    : null;
                console.log(`🔍 KCS Click - kcsId: ${kcsId}, Found:`, !!resultData);
                sourceType = 'kcs';
            } else if (source === 'github') {
                // Use data-global-idx (_originalIndex embedded at render time)
                const gIdx = resultItem.getAttribute('data-global-idx');
                resultData = gIdx != null
                    ? window.lastSearchResults?.github?.results?.find(r => String(r._originalIndex) === gIdx)
                    : null;
                sourceType = 'github';
            } else if (source === 'gitlab') {
                const gIdx = resultItem.getAttribute('data-global-idx');
                resultData = gIdx != null
                    ? window.lastSearchResults?.gitlab?.results?.find(r => String(r._originalIndex) === gIdx)
                    : null;
                sourceType = 'gitlab';
            }
        }

        if (resultData) {
            console.log('✅ Found data for source:', source, resultData);
            // Remove selected class from all result items
            document.querySelectorAll('.result-item').forEach(r => r.classList.remove('selected'));
            // Add selected class to clicked item
            resultItem.classList.add('selected');
            showDetailPanel(resultData, sourceType);
        } else {
            console.error('❌ No data found for source:', source);
        }
    };

    document.addEventListener('click', window.resultClickHandler);
    console.log('✅ Event delegation click handler attached');
}

// ============================================================================
// UNIVERSAL HEADER SEARCH (Works on all pages)
// ============================================================================

function setupUniversalHeaderSearch() {
    const searchInput = document.querySelector('.search-input');
    const searchButton = document.querySelector('.search-button');

    if (!searchInput || !searchButton) return;

    // Get current page path
    const currentPath = window.location.pathname;
    const isMainPage = currentPath.includes('/main') || currentPath === '/seekr/' || currentPath === '/';

    if (isMainPage) {
        // Main page: search is already handled by performSearch()
        return;
    }

    // Other pages (Settings, Recent Searches): redirect to main with query
    const handleHeaderSearch = () => {
        const query = searchInput.value.trim();
        if (query) {
            sessionStorage.setItem('pendingSearch', query);
            window.location.href = '/seekr/main';
        }
    };

    searchButton.addEventListener('click', handleHeaderSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleHeaderSearch();
        }
    });
}

// Run on all pages
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupUniversalHeaderSearch);
} else {
    setupUniversalHeaderSearch();
}

/* ============================================ */
/* RECENT SEARCHES PAGE JAVASCRIPT */
/* ============================================ */

// Recent Searches JavaScript
let searchHistory = [];
let currentDatePage = 1;
let dateGroups = [];

async function loadSearchHistory() {
    try {
        const response = await fetch('/api/search/history');
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/seekr/login';
                return;
            }
            throw new Error('Failed to load search history');
        }

        const data = await response.json();
        searchHistory = data.history || [];

        document.getElementById('loadingState').style.display = 'none';

        if (searchHistory.length === 0) {
            document.getElementById('emptyState').style.display = 'block';
        } else {
            document.getElementById('searchHistory').style.display = 'block';
            renderSearchHistory();
        }
    } catch (error) {
        console.error('Error loading search history:', error);
        document.getElementById('loadingState').style.display = 'none';
        document.getElementById('emptyState').style.display = 'block';
    }
}

function renderSearchHistory() {
    const container = document.getElementById('searchHistory');

    // Group searches by date
    const groupedByDate = {};

    searchHistory.forEach(search => {
        const date = new Date(search.timestamp);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        let dateLabel;
        if (isSameDay(date, today)) {
            dateLabel = 'Today';
        } else if (isSameDay(date, yesterday)) {
            dateLabel = 'Yesterday';
        } else {
            dateLabel = formatDate(date);
        }

        if (!groupedByDate[dateLabel]) {
            groupedByDate[dateLabel] = [];
        }
        groupedByDate[dateLabel].push(search);
    });

    // Convert to array for pagination
    dateGroups = Object.keys(groupedByDate).map(dateLabel => ({
        label: dateLabel,
        searches: groupedByDate[dateLabel]
    }));

    // Render current page (one date per page)
    renderCurrentDatePage();
}

function renderCurrentDatePage() {
    const container = document.getElementById('searchHistory');

    if (dateGroups.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Get current date group
    const currentGroup = dateGroups[currentDatePage - 1];

    let html = `
        <div class="date-group">
            <div class="date-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                ${currentGroup.label}
            </div>
            <div class="search-history-list">
                ${renderSearchItems(currentGroup.searches)}
            </div>
        </div>
    `;

    // Add pagination controls
    html += createDatePagination();

    container.innerHTML = html;
}

function createDatePagination() {
    const totalPages = dateGroups.length;
    if (totalPages <= 1) return '';

    let html = '<div class="pagination-controls">';

    // Previous button
    html += `<button class="pagination-btn" ${currentDatePage === 1 ? 'disabled' : ''} onclick="changeRecentSearchPage(${currentDatePage - 1})">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
        Previous
    </button>`;

    // Page info
    html += `<div class="pagination-info" style="padding: 0 1rem; color: #666; font-size: 0.875rem;">
        Page ${currentDatePage}/${totalPages}
    </div>`;

    // Next button
    html += `<button class="pagination-btn" ${currentDatePage === totalPages ? 'disabled' : ''} onclick="changeRecentSearchPage(${currentDatePage + 1})">
        Next
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
    </button>`;

    html += '</div>';

    return html;
}

function changeRecentSearchPage(page) {
    if (page < 1 || page > dateGroups.length) return;
    currentDatePage = page;
    renderCurrentDatePage();
}

function renderSearchItems(searches) {
    return searches.map(search => {
        const time = formatTime(new Date(search.timestamp));
        const sources = search.sources || [];

        return `
            <div class="search-history-item" onclick="repeatSearch('${escapeHtml(search.query)}')">
                <div class="search-item-left">
                    <div class="search-query">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"/>
                            <path d="m21 21-4.35-4.35"/>
                        </svg>
                        ${escapeHtml(search.query)}
                    </div>
                    <div class="search-metadata">
                        <div class="metadata-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                                <polyline points="12 6 12 12 16 14"/>
                            </svg>
                            ${time}
                        </div>
                        <div class="metadata-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M9 11l3 3L22 4"/>
                                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                            </svg>
                            ${search.results_count} result${search.results_count !== 1 ? 's' : ''}
                        </div>
                    </div>
                </div>
                <div class="search-sources">
                    ${sources.map(source => `<span class="source-badge">${source}</span>`).join('')}
                </div>
            </div>
        `;
    }).join('');
}

function repeatSearch(query) {
    // Save query to sessionStorage and redirect to search page
    sessionStorage.setItem('pendingSearch', query);
    window.location.href = '/seekr/main';
}

function isSameDay(date1, date2) {
    return date1.getFullYear() === date2.getFullYear() &&
           date1.getMonth() === date2.getMonth() &&
           date1.getDate() === date2.getDate();
}

function formatDate(date) {
    const options = { month: 'long', day: 'numeric', year: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

function formatTime(date) {
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize Recent Searches page
function initRecentSearchesPage() {
    // Check if we're on the recent searches page
    if (!document.getElementById('searchHistory')) return;

    // Header search functionality
    const headerSearchBtn = document.getElementById('headerSearchBtn');
    const headerSearchInput = document.getElementById('headerSearchInput');

    if (headerSearchBtn) {
        headerSearchBtn.addEventListener('click', () => {
            const query = headerSearchInput.value.trim();
            if (query) {
                sessionStorage.setItem('pendingSearch', query);
                window.location.href = '/seekr/main';
            }
        });
    }

    if (headerSearchInput) {
        headerSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const query = e.target.value.trim();
                if (query) {
                    sessionStorage.setItem('pendingSearch', query);
                    window.location.href = '/seekr/main';
                }
            }
        });
    }

    // Load history on page load
    loadSearchHistory();
}

// Run Recent Searches initialization
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRecentSearchesPage);
} else {
    initRecentSearchesPage();
}

/* ============================================ */
/* SETTINGS PAGE JAVASCRIPT */
/* ============================================ */

function initSettingsPage() {
    // Only run on the settings page (which has .settings-content), not on main search page
    if (!document.querySelector('.settings-content')) return;

    const searchButton = document.querySelector('.search-button');
    const searchInput = document.querySelector('.search-input');

    if (!searchButton || !searchInput) return;

    function performSearch() {
        const query = searchInput.value.trim();
        if (query) {
            // Redirect to main page with search query
            window.location.href = `/main?q=${encodeURIComponent(query)}`;
        }
    }

    searchButton.addEventListener('click', performSearch);

    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });
}

// Run Settings initialization
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSettingsPage);
} else {
    initSettingsPage();
}

// ============================================================================
// AI SUMMARY + CHAT
// ============================================================================

let _aiCaseNumber   = null;
let _aiCaseData     = null;
let _aiChatHistory  = [];
let _aiSummaryHtml  = '';

function resetAISummaryPanel() {
    _aiCaseNumber  = null;
    _aiCaseData    = null;
    _aiChatHistory = [];
    _aiSummaryHtml = '';
    const trigger    = document.getElementById('ai-summary-trigger');
    const result     = document.getElementById('ai-summary-result');
    const chatBox    = document.getElementById('ai-chat-box');
    const btn        = document.getElementById('ai-summary-btn');
    const msgs       = document.getElementById('ai-chat-messages');
    const regenBar   = document.getElementById('ai-regenerate-bar');
    if (trigger)  trigger.style.display = 'block';
    if (result)   { result.style.display = 'none'; result.innerHTML = ''; }
    if (chatBox)  chatBox.style.display  = 'none';
    if (btn)      { btn.disabled = false; btn.textContent = '🤖 Generate AI Summary'; }
    if (msgs)     msgs.innerHTML = '';
    if (regenBar) regenBar.remove();
}

function setAIContext(caseNumber, caseData) {
    if (_aiCaseNumber !== caseNumber) {
        resetAISummaryPanel();
        _aiCaseNumber = caseNumber;
        _aiCaseData   = caseData;
    }
}

async function triggerAISummary() {
    if (!_aiCaseNumber) {
        alert('Please open an SFDC case first.');
        return;
    }
    const btn     = document.getElementById('ai-summary-btn');
    const result  = document.getElementById('ai-summary-result');
    const trigger = document.getElementById('ai-summary-trigger');

    btn.disabled = true;
    btn.textContent = '⏳ Analyzing with Claude…';
    if (result) { result.style.display = 'block'; result.innerHTML = '<div class="ai-summary-loading"><div class="loading-spinner"></div><p>Generating AI summary — this may take up to 30 seconds…</p></div>'; }

    try {
        const resp = await fetch('/api/ai/case-summary', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                case_number: _aiCaseNumber,
                case_data:   _aiCaseData || {}
            })
        });
        const data = await resp.json();

        if (data.timeout) {
            result.innerHTML = '<p style="color:#fc8181;">⏱ Claude timed out. <button onclick="triggerAISummary()">🔄 Retry</button></p>';
            btn.disabled = false;
            btn.textContent = '🤖 Generate AI Summary';
            return;
        }
        if (data.error && !data.html) {
            result.innerHTML = `<p style="color:#fc8181;">⚠ ${escapeHtml(data.error)}</p>`;
            btn.disabled = false;
            btn.textContent = '🤖 Retry AI Summary';
            return;
        }

        _aiSummaryHtml = data.html || '';

        // Build linked resources bar
        let linkedHtml = '';
        const lr = data.linked_resources || {};
        const kcsLinks  = lr.kcs      || [];
        const jiraLinks = lr.jira     || [];
        const bzLinks   = lr.bugzilla || [];
        const hasLinks  = kcsLinks.length + jiraLinks.length + bzLinks.length > 0;
        if (hasLinks) {
            linkedHtml = '<div class="ai-linked-bar"><strong>🔗 Linked in Case:</strong> ';
            kcsLinks.slice(0,5).forEach(url => {
                const id = (url.match(/\/(\d+)/) || [])[1] || 'KCS';
                linkedHtml += `<a href="${url}" target="_blank" class="ai-pill ai-kcs-pill">📚 KCS-${id}</a> `;
            });
            jiraLinks.slice(0,6).forEach(j => {
                linkedHtml += `<a href="${escapeHtml(j.url)}" target="_blank" class="ai-pill ai-jira-pill">🔧 ${escapeHtml(j.key)}</a> `;
            });
            bzLinks.slice(0,4).forEach(b => {
                linkedHtml += `<a href="${escapeHtml(b.url)}" target="_blank" class="ai-pill ai-bz-pill">🐛 BZ-${b.id}</a> `;
            });
            linkedHtml += '</div>';
        }

        const modeColor = data.mode === 'closed' ? '#68d391' : '#f6ad55';
        const modeLabel = data.mode === 'closed' ? '📋 Closed Case — Post-mortem Summary' : '🔄 Open Case — Analysis & Suggestions';

        result.innerHTML = `
            <div class="ai-mode-banner" style="background:${modeColor}18; border-left:4px solid ${modeColor}; padding:8px 12px; margin-bottom:12px; border-radius:4px;">
                <strong style="color:${modeColor};">${modeLabel}</strong>
                <span style="color:#718096; font-size:11px; margin-left:8px;">Status: ${escapeHtml(data.status || '')}</span>
            </div>
            ${linkedHtml}
            <div class="ai-summary-body">${data.html || ''}</div>`;

        if (trigger) trigger.style.display = 'none';
        const chatBox = document.getElementById('ai-chat-box');
        if (chatBox) chatBox.style.display = 'block';

        btn.textContent = '🔄 Regenerate Summary';
        btn.disabled = false;

        const existingRegen = document.getElementById('ai-regenerate-bar');
        if (existingRegen) existingRegen.remove();
        result.insertAdjacentHTML('afterend', `
            <div id="ai-regenerate-bar" style="padding: 8px 0 4px;">
                <button class="ai-summary-btn" style="font-size:12px; padding:6px 14px;" onclick="triggerAISummary()">🔄 Regenerate</button>
            </div>`);

    } catch (err) {
        result.innerHTML = `<p style="color:#fc8181;">⚠ Request failed: ${escapeHtml(err.message)}</p>`;
        btn.disabled = false;
        btn.textContent = '🤖 Retry AI Summary';
    }
}

async function sendAIChat() {
    const input   = document.getElementById('ai-chat-input');
    const sendBtn = document.getElementById('ai-chat-send');
    const msgs    = document.getElementById('ai-chat-messages');
    if (!input || !msgs) return;

    const question = input.value.trim();
    if (!question) return;

    const userBubble = document.createElement('div');
    userBubble.className = 'ai-chat-msg-user';
    userBubble.textContent = question;
    msgs.appendChild(userBubble);

    const clusterKeywords = ['check', 'cluster', 'node', 'pod', 'healthy', 'health', 'investigate', 'diagnose', 'logged in', 'login to cluster', 'i had login'];
    const isClusterQ = clusterKeywords.some(k => question.toLowerCase().includes(k));

    const loadingEl = document.createElement('div');
    loadingEl.className = 'ai-chat-msg-loading';
    loadingEl.textContent = isClusterQ
        ? '🖥️ Running cluster investigation (oc commands) — this may take up to 2 minutes…'
        : '🔍 Searching SOPs & KCS, then asking Claude…';
    msgs.appendChild(loadingEl);
    msgs.scrollTop = msgs.scrollHeight;

    input.value = '';
    sendBtn.disabled = true;

    const controller = new AbortController();
    const fetchTimeout = setTimeout(() => controller.abort(), 240000); // 4-minute client-side guard

    try {
        const resp = await fetch('/api/ai/case-chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            signal: controller.signal,
            body: JSON.stringify({
                case_number:  _aiCaseNumber,
                case_summary: _aiSummaryHtml,
                messages:     _aiChatHistory,
                question:     question
            })
        });
        clearTimeout(fetchTimeout);
        const data = await resp.json();
        loadingEl.remove();

        const aiBubble = document.createElement('div');
        aiBubble.className = 'ai-chat-msg-ai';
        if (data.error) {
            aiBubble.style.color = '#fc8181';
            aiBubble.textContent = '⚠ ' + data.error;
        } else {
            aiBubble.innerHTML = data.answer;

            if (data.refs && data.refs.length > 0) {
                const refBar = document.createElement('div');
                refBar.className = 'ai-chat-refs';
                refBar.innerHTML = '<span style="font-size:11px; color:#718096;">Sources: </span>' +
                    data.refs.map(r => `<a href="${r.url || '#'}" target="_blank" class="ai-pill ${r.type === 'kcs' ? 'ai-kcs-pill' : 'ai-sop-pill'}">${escapeHtml((r.title || 'Ref').substring(0, 35))}</a>`).join(' ');
                aiBubble.appendChild(refBar);
            }

            _aiChatHistory.push({role: 'user', content: question});
            _aiChatHistory.push({role: 'assistant', content: data.answer});
        }
        msgs.appendChild(aiBubble);
        msgs.scrollTop = msgs.scrollHeight;
    } catch (err) {
        clearTimeout(fetchTimeout);
        loadingEl.remove();
        const errBubble = document.createElement('div');
        errBubble.className = 'ai-chat-msg-ai';
        errBubble.style.color = '#fc8181';
        const msg = err.name === 'AbortError'
            ? '⚠ Cluster investigation timed out (>4 min). Try a more specific question, e.g. "check cluster operators" or "check node status".'
            : '⚠ Request failed: ' + err.message;
        errBubble.textContent = msg;
        msgs.appendChild(errBubble);
        msgs.scrollTop = msgs.scrollHeight;
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}
