import React, { createContext, useContext, useState, useEffect } from 'react';

const SettingsContext = createContext();

const AGILITY_STORAGE_KEY = 've_agility';
const CUES_STORAGE_KEY = 've_cues';

const readStoredAgility = () => {
  try {
    const stored = localStorage.getItem(AGILITY_STORAGE_KEY);
    return stored === 'high' || stored === 'low' ? stored : 'high';
  } catch {
    return 'high'; // localStorage unavailable (private mode / blocked)
  }
};

const readStoredCues = () => {
  try {
    // Default on: absent key means the user has never opted out.
    return localStorage.getItem(CUES_STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
};

/**
 * SettingsProvider — wraps the app and exposes:
 *   agility      : 'high' | 'low'  (user mobility; tunes backend time-to-contact urgency)
 *   setAgility   : setter
 *   cuesEnabled  : boolean         (non-speech earcon + vibration cues; default on)
 *   setCuesEnabled : setter
 *
 * Persists to localStorage ('ve_agility', 've_cues') and listens for
 * 'voice-set-agility' / 'voice-set-cues' CustomEvents so voice commands can
 * change them without a circular context dependency.
 */
export const SettingsProvider = ({ children }) => {
  const [agility, setAgility] = useState(readStoredAgility); // default: high
  const [cuesEnabled, setCuesEnabled] = useState(readStoredCues); // default: on

  useEffect(() => {
    try {
      localStorage.setItem(AGILITY_STORAGE_KEY, agility);
    } catch {
      // ignore write failures — the setting still applies for this session
    }
  }, [agility]);

  useEffect(() => {
    try {
      localStorage.setItem(CUES_STORAGE_KEY, cuesEnabled ? 'on' : 'off');
    } catch {
      // ignore write failures — the setting still applies for this session
    }
  }, [cuesEnabled]);

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

  useEffect(() => {
    const handler = (e) => {
      const requested = e.detail?.cues;
      if (typeof requested === 'boolean') {
        setCuesEnabled(requested);
      } else if (requested === 'on' || requested === 'off') {
        setCuesEnabled(requested === 'on');
      }
    };
    window.addEventListener('voice-set-cues', handler);
    return () => window.removeEventListener('voice-set-cues', handler);
  }, []);

  return (
    <SettingsContext.Provider value={{ agility, setAgility, cuesEnabled, setCuesEnabled }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => useContext(SettingsContext);
