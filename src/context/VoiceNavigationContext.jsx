import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';

const VoiceContext = createContext();

const ROUTE_NAMES = {
  '/dashboard/vision': 'Live Vision mode. You can say "start camera" to begin, or "help" for available commands.',
  '/dashboard/ocr': 'Smart Reader mode. You can say "read text" to extract text, or "help" for available commands.',
  '/dashboard/chat': 'Voice Chat mode. You can ask me anything.',
  '/dashboard/settings': 'Settings page. You can adjust application preferences here.',
  '/dashboard/demopurpose': 'Demo section. Explore sample features here.',
  '/dashboard': 'Dashboard. You can say "vision" for live vision, "read" for text recognition, or "chat" for voice assistant.',
  '/': 'Exiting application. Goodbye!'
};

export const VoiceProvider = ({ children }) => {
  const [isListening, setIsListening] = useState(false);
  const [lastCommand, setLastCommand] = useState('');
  
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);
  
  const recognitionRef = useRef(null);
  const isListeningRef = useRef(isListening); 
  const processingRef = useRef(false);
  const isSpeakingRef = useRef(false);          // true while TTS audio is playing
  const isRecognitionRunningRef = useRef(false); // true only when SpeechRecognition is actively running
  const recognitionSuspendedRef = useRef(false);
  const speechTokenRef = useRef(0);
  const [voice, setVoice] = useState(null);

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  // --- VOICE LOADING ---
  useEffect(() => {
    const loadVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) {
        const preferredVoice = voices.find(v => v.name.includes('Google US English')) || 
                               voices.find(v => v.name.includes('Zira')) || 
                               voices.find(v => v.lang.startsWith('en'));
        if (preferredVoice) setVoice(preferredVoice);
      }
    };
    window.speechSynthesis.onvoiceschanged = loadVoices;
    loadVoices();
  }, []);

  // --- AUTO-ANNOUNCE PAGE CHANGES ---
  useEffect(() => {
    const message = ROUTE_NAMES[location.pathname];
    if (message) setTimeout(() => speak(message), 200);
  }, [location.pathname]);

  // --- SPEECH RECOGNITION ---
  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
        isListeningRef.current = true;
        isRecognitionRunningRef.current = true;
      };
      // Only auto-restart if user still wants to listen AND TTS is not currently playing
      recognition.onend = () => {
        isRecognitionRunningRef.current = false;
        if (isListeningRef.current && !isSpeakingRef.current && !recognitionSuspendedRef.current) {
          try { recognition.start(); } catch (e) {}
        } else if (!isListeningRef.current) {
          setIsListening(false);
        }
      };
      recognition.onerror = () => {
        isRecognitionRunningRef.current = false;
        isListeningRef.current = false;
        setIsListening(false);
      };
      
      recognition.onresult = (event) => {
        const transcript = event.results[event.resultIndex][0].transcript.toLowerCase().trim();
        console.log("Heard:", transcript);
        setLastCommand(transcript);
        
        // Skip if TTS is currently playing OR we're still in command-lock cooldown
        if (!processingRef.current && !isSpeakingRef.current) {
          processingRef.current = true;
          processCommand(transcript);
          // Base lock — speak() manages its own TTS cooldown.
          setTimeout(() => { processingRef.current = false; }, 1500);
        } else {
          console.debug('Ignored during speech cooldown:', transcript);
        }
      };
      
      recognitionRef.current = recognition;
    }
    return () => { if (recognitionRef.current) recognitionRef.current.stop(); };
  }, []);

  // --- COMMAND LOGIC ---
  const processCommand = (cmd) => {
    console.log('Processing command:', cmd);
    const matches = (keywords) => keywords.some(k => cmd.includes(k));
    const currentPath = locationRef.current.pathname;
    const sceneQuestionPatterns = [
      'where is', "where's", 'where are', 'where can i find', 'find my', 'find the',
      'find a ', 'find an ', 'can you find', 'could you find', 'locate', 'look for',
      'can you see', 'do you see', 'is there',
      'what do you see', 'what can you see',
      'describe the scene', 'describe what you see', 'what is around me', "what's around me",
      'what is here', "what's here", 'what is on', "what's on", 'anything on',
      'anything else', 'what else', 'next to', 'beside', 'near it', 'how far',
      'what distance', 'which side', 'what side', 'left or right', 'within reach',
      'can i reach', 'how do i reach', 'how should i reach', 'check again', 'try again',
      'look again', 'see it now', 'where is it now', 'how many', 'count the',
      'what is to my left', 'what is to my right', 'what is in front',
    ];
    const isVisualPresenceQuestion = /^is (?:my|the|a|an) .+ (?:here|visible|in view)$/.test(cmd);
    
    // Function to stop camera with proper event dispatching
    const stopCamera = () => {
      console.log('Stopping camera...');
      // Dispatch both specific and generic stop events
      window.dispatchEvent(new CustomEvent('voice-stop-camera'));
      window.dispatchEvent(new CustomEvent('stop-all'));
    };

    // Function to switch between front and back cameras
    const switchCamera = () => {
      console.log('Switching camera...');
      window.dispatchEvent(new CustomEvent('voice-switch-camera'));
    };

    // 0. MODE SWITCHING — priority / naive engine toggle
    if (matches(['priority mode', 'switch to priority', 'enable priority', 'activate priority', 'use priority'])) {
      window.dispatchEvent(new CustomEvent('voice-set-mode', { detail: { mode: 'priority' } }));
      speak("Priority mode activated. Only actionable hazards will be announced automatically.");
      return;
    }
    if (matches(['naive mode', 'switch to naive', 'enable naive', 'activate naive', 'use naive', 'announce all', 'all objects'])) {
      window.dispatchEvent(new CustomEvent('voice-set-mode', { detail: { mode: 'naive' } }));
      speak("Naive mode activated. All detected objects will be announced.");
      return;
    }

    // Camera questions take precedence over generic words such as "help" or "stop".
    if (matches(sceneQuestionPatterns) || isVisualPresenceQuestion) {
      if (currentPath.includes('vision')) {
        window.dispatchEvent(new CustomEvent('voice-scene-question', { detail: { question: cmd } }));
      } else {
        navigate('/dashboard/vision');
        speak("Opening Vision mode. Start the camera, then ask me that again.");
      }
      return;
    }

    // 1. HELP COMMANDS - Comprehensive help system
    if (matches(['help', 'what can i say', 'commands', 'options', 'what can you do', 'list commands', 'show me commands', 'what are my options'])) {
      const helpMessage = "You can say: start camera; find my remote; what's on this table; what's next to it; what do you see; switch camera; priority mode; read text; or stop camera.";
      speak(helpMessage);
      return;
    }

    // 2. CAMERA SWITCHING COMMANDS - Handle camera switching
    if (matches(['switch camera', 'change camera', 'front camera', 'back camera', 'rear camera', 'flip camera', 
                'switch to front', 'switch to back', 'switch to rear', 'change to front', 'change to back',
                'toggle camera', 'other camera', 'next camera'])) {
      if (currentPath.includes('vision')) {
        switchCamera();
      } else {
        speak("Please start the camera first by saying 'start camera'.");
      }
      return;
    }

    // 3. STOP COMMANDS - Handle all stop-related commands first
    if (matches(['stop', 'stop camera', 'turn off camera', 'shut down camera', 'end camera', 'close camera', 
                'stop vision', 'turn off vision', 'stop seeing', 'stop looking', 'stop scanning',
                'that\'s enough', 'enough', 'all done', 'i\'m done', 'finish', 'end session',
                'turn it off', 'shut it down', 'stop that', 'stop now'])) {
      stopCamera();
      return;
    }

    // 3. CAMERA START COMMANDS
    if (matches(['start camera', 'turn on camera', 'begin vision', 'start vision',
                'start seeing', 'begin seeing', 'open camera', 'activate camera'])) {
      if (currentPath.includes('vision')) {
        window.dispatchEvent(new CustomEvent('voice-start-camera'));
      } else {
        navigate('/dashboard/vision');
        setTimeout(() => window.dispatchEvent(new CustomEvent('voice-start-camera')), 1500);
      }
      return;
    }

    // 10. NAVIGATION COMMANDS - Enhanced with more natural language options
    if (matches(['vision', 'camera', 'live vision', 'see around', 'open vision', 'go to vision', 'show me around'])) {
      if (!currentPath.includes('vision')) {
        navigate('/dashboard/vision');
        speak("Opening Live Vision mode. Say 'start camera' to begin, or 'help' for more options.");
      } else {
        speak("You're already in Vision mode. Try saying 'start camera' or 'what do you see?'");
      }
    }
    else if (matches(['read', 'ocr', 'text', 'smart reader', 'read text', 'scan document', 'scan text', 'extract text', 'read document', 'read paper', 'read paper document', 'read printed text', 'read text from camera'])) {
      if (!currentPath.includes('ocr')) {
        navigate('/dashboard/ocr');
        speak("Opening Smart Reader. Position your document in view and say 'read text' to begin.");
      } else {
        speak("You're already in Smart Reader. Position your document and say 'read text' to start.");
      }
    }
    // SCENE QUESTIONS — handled inline via Vision backend, no navigation
    else if (matches(['chat', 'voice chat', 'talk', 'assistant', 'ai', 'ask ai', 'ask question', 'i have a question', 'i need help', 'can you help', 'help me',
                    'talk to assistant', 'start chat', 'open chat', 'chat with ai', 'ask something', 'i want to ask', 'can i ask', 'hey assistant',
                    'virtual assistant', 'virtual eye', 'hey virtual eye', 'okay virtual eye', 'hello assistant', 'hey ai', 'okay ai', 'hello ai',
                    'i need information', 'tell me about', 'i want to know', 'can you tell me'])) {
      
      if (!currentPath.includes('chat')) {
        speak("Opening Chat. How can I assist you today?");
        navigate('/dashboard/chat');
      } else {
        speak("I'm here to help. What would you like to know?");
      }
    }
    else if (matches(['settings', 'preferences', 'options', 'configure', 'adjust settings', 'change settings', 'app settings', 'application settings', 'configure app'])) {
      if (!currentPath.includes('settings')) {
        navigate('/dashboard/settings');
        speak("Opening Settings. You can adjust your preferences here.");
      } else {
        speak("You're already in Settings. What would you like to adjust?");
      }
    }
    else if (matches(['demo', 'examples', 'show me', 'demonstration', 'show features', 'show me features', 'show me demo', 'what can you do'])) {
      if (!currentPath.includes('demopurpose')) {
        navigate('/dashboard/demopurpose');
        speak("Opening Demo section. Here you can explore sample features and capabilities.");
      } else {
        speak("You're already in the Demo section. What would you like to try?");
      }
    }
    else if (matches(['home', 'dashboard', 'main menu', 'go back', 'main screen', 'go to home', 'back to home', 'main dashboard', 'back to dashboard'])) {
      if (currentPath !== '/dashboard') {
        navigate('/dashboard');
        speak("Returning to Dashboard. You can say 'vision', 'read text', or 'chat' to continue.");
      } else {
        speak("You're already on the Dashboard. Where would you like to go?");
      }
    }
    else if (matches(['exit', 'logout', 'goodbye', 'close app', 'quit', 'close application', 'end session', 'i am done', 'that\'s all'])) {
      if (confirm("Are you sure you want to exit?")) {
        navigate('/');
        speak("Goodbye! Thank you for using Virtual Eye. Have a great day!");
      } else {
        speak("I'll keep the application running. What would you like to do next?");
      }
    }
    
    // 11. EMERGENCY COMMANDS
    else if (matches(['sos', 'help', 'emergency', 'urgent', 'call for help'])) {
      speak("Emergency alert triggered! Sending your location to emergency contacts.");
      toast.error("EMERGENCY ALERT: Your location has been shared with emergency contacts!");
      // Additional emergency actions can be added here
    }
    
    // 12. GENERAL CONVERSATION
    else if (matches(['thank you', 'thanks', 'that\'s all', 'that is all', 'i\'m done'])) {
      speak("You're welcome! Is there anything else I can help you with?");
    }
    else if (matches(['who are you', 'what are you', 'introduce yourself'])) {
      speak("I am your Virtual Eye assistant, here to help you navigate and understand your surroundings. I can describe what I see, read text, and answer your questions.");
    }
    else if (matches(['what time is it', 'current time', 'what\'s the time'])) {
      const time = new Date().toLocaleTimeString('en-US', {hour: '2-digit', minute:'2-digit'});
      speak(`The current time is ${time}`);
    }
    else if (matches(['what day is it', 'what\'s today', 'current date'])) {
      const date = new Date().toLocaleDateString('en-US', {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});
      speak(`Today is ${date}`);
    }
  };

  const toggleListening = () => {
    if (isListeningRef.current) {
      isListeningRef.current = false;
      recognitionSuspendedRef.current = false;
      recognitionRef.current.stop();
      speak("Voice paused.");
      setIsListening(false);
    } else {
      isListeningRef.current = true;
      recognitionSuspendedRef.current = false;
      try { recognitionRef.current.start(); speak("I am listening."); } catch(e) {}
      setIsListening(true);
    }
  };

  const cancelSpeech = () => {
    speechTokenRef.current += 1;
    window.speechSynthesis.cancel();
    isSpeakingRef.current = false;
    processingRef.current = false;

    if (isListeningRef.current && !recognitionSuspendedRef.current && !isRecognitionRunningRef.current) {
      setTimeout(() => {
        try { recognitionRef.current?.start(); } catch (e) {}
      }, 150);
    }
  };

  const suspendListening = () => {
    recognitionSuspendedRef.current = true;
    if (isRecognitionRunningRef.current) {
      try { recognitionRef.current?.stop(); } catch (e) {}
    }
  };

  const resumeListening = () => {
    recognitionSuspendedRef.current = false;
    if (isListeningRef.current && !isSpeakingRef.current && !isRecognitionRunningRef.current) {
      setTimeout(() => {
        if (
          !isListeningRef.current
          || recognitionSuspendedRef.current
          || isSpeakingRef.current
          || isRecognitionRunningRef.current
        ) return;
        try { recognitionRef.current?.start(); } catch (e) {}
      }, 150);
    }
  };

  const speak = (text) => {
    const speechToken = speechTokenRef.current + 1;
    speechTokenRef.current = speechToken;
    window.speechSynthesis.cancel();
    const voices = window.speechSynthesis.getVoices();
    // Retry if voices not loaded yet
    if (voices.length === 0) { setTimeout(() => speak(text), 100); return; }

    // Block commands immediately and mark TTS as active
    isSpeakingRef.current = true;
    processingRef.current = true;

    // Only stop recognition if it's actually running — avoids spurious onend/restart cycles
    if (isRecognitionRunningRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
    }

    const selectedVoice = voice ||
      voices.find(v => v.name.includes('Google US English')) ||
      voices.find(v => v.lang.startsWith('en'));

    const utterance = new SpeechSynthesisUtterance(text);
    if (selectedVoice) utterance.voice = selectedVoice;

    // Estimate TTS duration (~65ms per character, min 800ms) for safety fallback
    const estimatedMs = Math.max(800, text.length * 65);

    const onTTSDone = () => {
      if (speechToken !== speechTokenRef.current || !isSpeakingRef.current) return;
      isSpeakingRef.current = false;
      // Clear the command lock before recognition resumes so the next question is not dropped.
      setTimeout(() => {
        if (speechToken === speechTokenRef.current) {
          processingRef.current = false;
        }
      }, 350);
      // Resume mic only if user wants to listen and it's not already running
      if (
        isListeningRef.current
        && !recognitionSuspendedRef.current
        && !isRecognitionRunningRef.current
      ) {
        setTimeout(() => {
          if (speechToken !== speechTokenRef.current) return;
          try { recognitionRef.current.start(); } catch (e) {}
        }, 600); // 600ms gap lets echo fully fade
      }
    };

    utterance.onend = onTTSDone;
    utterance.onerror = onTTSDone;

    // Safety fallback: browsers sometimes don't fire onend — release after estimated duration + 2s buffer
    setTimeout(() => {
      if (speechToken === speechTokenRef.current && isSpeakingRef.current) {
        onTTSDone();
      }
    }, estimatedMs + 2000);

    window.speechSynthesis.speak(utterance);
  };

  return (
    <VoiceContext.Provider value={{
      isListening,
      toggleListening,
      lastCommand,
      speak,
      cancelSpeech,
      suspendListening,
      resumeListening,
    }}>
      {children}
    </VoiceContext.Provider>
  );
};

export const useVoice = () => useContext(VoiceContext);
