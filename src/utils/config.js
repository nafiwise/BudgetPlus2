import { Capacitor } from '@capacitor/core';

// Default remote URL from build-time Vite environment variable
const BUILD_TIME_API_URL = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');

export function isNativePlatform() {
  try {
    return Capacitor.isNativePlatform();
  } catch {
    return false;
  }
}

export function getCustomApiBase() {
  try {
    return (localStorage.getItem('budgetplus_custom_api_url') || '').trim().replace(/\/+$/, '');
  } catch {
    return '';
  }
}

export function setCustomApiBase(url) {
  try {
    const cleaned = (url || '').trim().replace(/\/+$/, '');
    if (cleaned) {
      localStorage.setItem('budgetplus_custom_api_url', cleaned);
    } else {
      localStorage.removeItem('budgetplus_custom_api_url');
    }
  } catch {}
}

export function getApiBaseUrl() {
  // 1. User manual override (stored in preferences/localStorage)
  const custom = getCustomApiBase();
  if (custom) return custom;

  // 2. Build-time environment variable (e.g. VITE_API_URL=https://my-backend.example.com)
  if (BUILD_TIME_API_URL) return BUILD_TIME_API_URL;

  // 3. In browser development/localhost, use relative path '' so Vite proxy handles /api
  if (!isNativePlatform() && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
    return '';
  }

  // 4. In native Capacitor on iOS (which runs from capacitor://localhost or budgetplus://localhost),
  // default to remote backend if window config exists, otherwise check stored or return ''
  if (typeof window !== 'undefined' && window.__BUDGETPLUS_BACKEND_URL__) {
    return window.__BUDGETPLUS_BACKEND_URL__.replace(/\/+$/, '');
  }

  return '';
}

