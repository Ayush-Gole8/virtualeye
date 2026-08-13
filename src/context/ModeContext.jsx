import React, { createContext, useContext, useState, useEffect } from 'react';

const ModeContext = createContext();

/**
 * ModeProvider — wraps the app and exposes:
 *   mode        : 'priority' | 'naive'
 *   setMode     : setter
 *   toggleMode  : convenience toggle
 *
 * Also listens for 'voice-set-mode' CustomEvents dispatched by VoiceNavigationContext
 * so voice commands can switch the mode without a circular context dependency.
 */
export const ModeProvider = ({ children }) => {
  const [mode, setMode] = useState('priority'); // default: priority engine active

  const toggleMode = () =>
    setMode(prev => (prev === 'priority' ? 'naive' : 'priority'));

  // Voice command bridge — VoiceNavigationContext fires this event
  useEffect(() => {
    const handler = (e) => {
      const requested = e.detail?.mode;
      if (requested === 'priority' || requested === 'naive') {
        setMode(requested);
      }
    };
    window.addEventListener('voice-set-mode', handler);
    return () => window.removeEventListener('voice-set-mode', handler);
  }, []);

  return (
    <ModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </ModeContext.Provider>
  );
};

export const useMode = () => useContext(ModeContext);
