/* Login and first-run setup. Kept separate so the CSP can forbid inline JS. */
(() => {
  'use strict';
  const form = document.getElementById('auth-form');
  const password = document.getElementById('password');
  const confirm = document.getElementById('confirm');
  const errorBox = document.getElementById('auth-error');
  const submit = document.getElementById('auth-submit');
  const mode = document.body.dataset.mode || 'login';
  const t = (key) => (window.ofdlI18n ? window.ofdlI18n.t(key) : key);

  function setError(text) {
    errorBox.textContent = text || '';
  }

  async function request(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    let data = {};
    try { data = await response.json(); } catch (_) { /* empty body */ }
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('');
    const value = password.value;
    if (value.length < 10) {
      setError(t('Das Passwort muss mindestens 10 Zeichen lang sein.'));
      password.focus();
      return;
    }
    if (mode === 'setup' && value !== confirm.value) {
      setError(t('Die Passwörter stimmen nicht überein.'));
      confirm.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = mode === 'setup' ? t('Wird gespeichert …') : t('Wird angemeldet …');
    try {
      if (mode === 'setup') {
        await request('/api/setup', { password: value, confirm: confirm.value });
      } else {
        await request('/api/login', { password: value });
      }
      window.location.replace('/');
    } catch (error) {
      if (error.status === 401 && error.data && error.data.setup_required) {
        window.location.replace('/setup');
        return;
      }
      if (error.status === 409 && mode === 'setup') {
        window.location.replace('/login');
        return;
      }
      setError(t(error.message) || t('Anmeldung fehlgeschlagen.'));
      password.select();
    } finally {
      submit.disabled = false;
      submit.textContent = mode === 'setup' ? t('Passwort speichern') : t('Anmelden');
    }
  });

  password.focus();
})();
