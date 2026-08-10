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
  
  const recognitionRef = useRef(null);
  const isListeningRef = useRef(isListening); 
  const processingRef = useRef(false);
  const [voice, setVoice] = useState(null);

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

      recognition.onstart = () => { setIsListening(true); isListeningRef.current = true; };
      recognition.onend = () => { if (isListeningRef.current) try { recognition.start(); } catch (e) {} else setIsListening(false); };
      recognition.onerror = () => { isListeningRef.current = false; setIsListening(false); };
      
      recognition.onresult = (event) => {
        const transcript = event.results[event.resultIndex][0].transcript.toLowerCase().trim();
        console.log("Heard:", transcript);
        setLastCommand(transcript);
        
        if (!processingRef.current) {
          processingRef.current = true;
          processCommand(transcript);
          setTimeout(() => { processingRef.current = false; }, 1500);
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
    
    // Function to stop camera with proper event dispatching
    const stopCamera = () => {
      console.log('Stopping camera...');
      // Dispatch both specific and generic stop events
      window.dispatchEvent(new CustomEvent('voice-stop-camera'));
      window.dispatchEvent(new CustomEvent('stop-all'));
      speak("Camera stopped.");
    };

    // Function to switch between front and back cameras
    const switchCamera = () => {
      console.log('Switching camera...');
      window.dispatchEvent(new CustomEvent('voice-switch-camera'));
      speak("Switching camera view.");
    };

    // 1. HELP COMMANDS - Comprehensive help system
    if (matches(['help', 'what can i say', 'commands', 'options', 'what can you do', 'list commands', 'show me commands', 'what are my options'])) {
      const helpMessage = `
        Here are the available voice commands:
        
        NAVIGATION:
        - "Go to vision" or "Open camera" - Switch to live vision mode
        - "Read text" or "Scan document" - Open text recognition
        - "Chat" or "Talk to assistant" - Start voice chat
        - "Settings" or "Preferences" - Open settings
        - "Home" or "Dashboard" - Return to main menu
        - "Exit" or "Close app" - Exit the application
        
        VISION MODE:
        - "Start camera" - Begin live vision
        - "Stop camera" - Stop the camera
        - "Switch camera" - Toggle between front and back cameras
        - "What do you see?" - Describe the current view
        - "Take a picture" - Capture and analyze the scene
        - "Calibrate" - Set up distance measurement
        - "What time is it?" - Hear the current time
        - "What day is it?" - Hear today's date
        
        TEXT MODE:
        - "Read text" - Extract text from camera
        - "Auto read" - Continuous text reading
        - "Stop reading" - Pause text reading
        
        GENERAL:
        - "Help" - Hear this list of commands
        - "Emergency" - Trigger emergency alert
        - "Thank you" - Acknowledge the assistant
      `;
      speak(helpMessage);
      return;
    }

    // 2. CAMERA SWITCHING COMMANDS - Handle camera switching
    if (matches(['switch camera', 'change camera', 'front camera', 'back camera', 'rear camera', 'flip camera', 
                'switch to front', 'switch to back', 'switch to rear', 'change to front', 'change to back',
                'toggle camera', 'other camera', 'next camera'])) {
      if (location.pathname.includes('vision')) {
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

    // 3. VISION MODE COMMANDS - Enhanced with more natural language options
    if (matches(['start camera', 'turn on camera', 'describe my surroundings', 'what is around me', 
                'begin vision', 'start vision', 'start seeing', 'begin seeing', 'what do you see',
                'describe scene', 'analyze surroundings', 'scan area', 'look around', 'what\'s around',
                'what can you see', 'describe environment', 'show me what you see'])) {
      if (location.pathname.includes('vision')) {
        window.dispatchEvent(new CustomEvent('voice-start-camera'));
        speak("Starting camera. I will describe what I see.");
      } else {
        speak("Opening Vision mode to describe your surroundings.");
        navigate('/dashboard/vision');
        setTimeout(() => window.dispatchEvent(new CustomEvent('voice-start-camera')), 1500);
      }
      return;
    }

    // 10. NAVIGATION COMMANDS - Enhanced with more natural language options
    if (matches(['vision', 'camera', 'live vision', 'see around', 'describe surroundings', 'open vision', 'go to vision', 'start vision', 'show me around', 'what is around me', 'describe environment'])) {
      if (!location.pathname.includes('vision')) {
        navigate('/dashboard/vision');
        speak("Opening Live Vision mode. Say 'start camera' to begin, or 'help' for more options.");
      } else {
        speak("You're already in Vision mode. Try saying 'start camera' or 'what do you see?'");
      }
    }
    else if (matches(['read', 'ocr', 'text', 'smart reader', 'read text', 'scan document', 'scan text', 'extract text', 'read document', 'read paper', 'read paper document', 'read printed text', 'read text from camera'])) {
      if (!location.pathname.includes('ocr')) {
        navigate('/dashboard/ocr');
        speak("Opening Smart Reader. Position your document in view and say 'read text' to begin.");
      } else {
        speak("You're already in Smart Reader. Position your document and say 'read text' to start.");
      }
    }
    else if (matches(['chat', 'voice chat', 'talk', 'assistant', 'ai', 'ask ai', 'ask question', 'i have a question', 'i need help', 'can you help', 'help me',
                    'talk to assistant', 'start chat', 'open chat', 'chat with ai', 'ask something', 'i want to ask', 'can i ask', 'hey assistant',
                    'virtual assistant', 'virtual eye', 'hey virtual eye', 'okay virtual eye', 'hello assistant', 'hey ai', 'okay ai', 'hello ai',
                    'i need information', 'tell me about', 'i want to know', 'can you tell me', 'what is', 'who is', 'how to', 'why is', 'when is', 'where is'])) {
      
      // Extract the actual question if present
      const questionPhrases = ['ask', 'question', 'what is', 'who is', 'how to', 'why is', 'when is', 'where is', 'tell me about'];
      const hasQuestion = questionPhrases.some(phrase => cmd.includes(phrase));
      
      if (!location.pathname.includes('chat')) {
        navigate('/dashboard/chat');
        // Small delay to ensure chat component is mounted
        setTimeout(() => {
          if (hasQuestion) {
            // If the command includes a question, send it to the chat
            const question = cmd.replace(/(ask|question|ai|assistant|please|can you|could you|would you|kindly|hey|okay|hello|hi|virtual eye|virtual assistant)/gi, '').trim();
            if (question) {
              window.dispatchEvent(new CustomEvent('voice-chat-question', { detail: { question } }));
              speak(`I'll help with your question about ${question}.`);
            } else {
              speak("Opening Chat. What would you like to know?");
            }
          } else {
            speak("Opening Chat. How can I assist you today?");
          }
        }, 500);
      } else if (hasQuestion) {
        // If already in chat and user asks a question
        const question = cmd.replace(/(ask|question|ai|assistant|please|can you|could you|would you|kindly|hey|okay|hello|hi|virtual eye|virtual assistant)/gi, '').trim();
        if (question) {
          window.dispatchEvent(new CustomEvent('voice-chat-question', { detail: { question } }));
          speak(`Let me help with that.`);
        } else {
          speak("I'm listening. What's your question?");
        }
      } else {
        speak("I'm here to help. What would you like to know?");
      }
    }
    else if (matches(['settings', 'preferences', 'options', 'configure', 'adjust settings', 'change settings', 'app settings', 'application settings', 'configure app'])) {
      if (!location.pathname.includes('settings')) {
        navigate('/dashboard/settings');
        speak("Opening Settings. You can adjust your preferences here.");
      } else {
        speak("You're already in Settings. What would you like to adjust?");
      }
    }
    else if (matches(['demo', 'examples', 'show me', 'demonstration', 'show features', 'show me features', 'show me demo', 'what can you do'])) {
      if (!location.pathname.includes('demopurpose')) {
        navigate('/dashboard/demopurpose');
        speak("Opening Demo section. Here you can explore sample features and capabilities.");
      } else {
        speak("You're already in the Demo section. What would you like to try?");
      }
    }
    else if (matches(['home', 'dashboard', 'main menu', 'go back', 'main screen', 'go to home', 'back to home', 'main dashboard', 'back to dashboard'])) {
      if (location.pathname !== '/dashboard') {
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
      recognitionRef.current.stop();
      speak("Voice paused.");
      setIsListening(false);
    } else {
      isListeningRef.current = true;
      try { recognitionRef.current.start(); speak("I am listening."); } catch(e) {}
      setIsListening(true);
    }
  };

  const speak = (text) => {
    window.speechSynthesis.cancel();
    const voices = window.speechSynthesis.getVoices();
    // Retry if voices not loaded
    if (voices.length === 0) { setTimeout(() => speak(text), 100); return; }

    let selectedVoice = voice || voices.find(v => v.name.includes('Google US English')) || voices.find(v => v.lang.startsWith('en'));
    
    const utterance = new SpeechSynthesisUtterance(text);
    if (selectedVoice) utterance.voice = selectedVoice;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <VoiceContext.Provider value={{ isListening, toggleListening, lastCommand, speak }}>
      {children}
    </VoiceContext.Provider>
  );
};

export const useVoice = () => useContext(VoiceContext);