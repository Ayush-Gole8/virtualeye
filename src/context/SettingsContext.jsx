import React, { createContext, useContext, useState, useEffect } from 'react';

const SettingsContext = createContext();

const AGILITY_STORAGE_KEY = 've_agility';

const readStoredAgility = () => {
  try {
    const stored = localStorage.getItem(AGILITY_STORAGE_KEY);
    return stored === 'high' || stored === 'low' ? stored : 'high';
  } catch {
    return 'high'; // localStorage unavailable (private mode / blocked)
  }
};

/**
 * SettingsProvider — wraps the app and exposes:
 *   agility     : 'high' | 'low'  (user mobility; tunes backend time-to-contact urgency)
 *   setAgility  : setter
 *
 * Persists to localStorage ('ve_agility') and listens for 'voice-set-agility'
 * CustomEvents so voice commands can change it without a circular context dependency.
 */
export const SettingsProvider = ({ children }) => {
  const [agility, setAgility] = useState(readStoredAgility); // default: high

  useEffect(() => {
    try {
      localStorage.setItem(AGILITY_STORAGE_KEY, agility);
    } catch {
      // ignore write failures — the setting still applies for this session
    }
  }, [agility]);

  // Voice command bridge — VoiceNavigationContext fires this event
  useEffect(() => {
    const handler = (e) => {
      const requested = e.detail?.agility;
      if (requested === 'high' || requested === 'low') {
        setAgility(requested);
      }
    };
    window.addEventListener('voice-set-agility', handler);
    return () => window.removeEventListener('voice-set-agility', handler);
  }, []);

  return (
    <SettingsContext.Provider value={{ agility, setAgility }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => useContext(SettingsContext);
