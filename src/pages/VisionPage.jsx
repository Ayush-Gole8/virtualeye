import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Camera, Square, Play, Mic, AlertCircle, CheckCircle, Zap, X, RefreshCw } from 'lucide-react';
import { useVoice } from '../context/VoiceNavigationContext';
import { useMode } from '../context/ModeContext';
import { useSettings } from '../context/SettingsContext';
import { selectCue, cueSignature, shouldFireCue, playEarcon, vibrateFor } from '../lib/cues';
import toast from 'react-hot-toast';
import './VisionPage.css';

// Backend API URL - supports both local Flask and ngrok
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// Helper to add ngrok bypass header
const getFetchOptions = (options = {}) => {
  const isNgrok = API_BASE_URL.includes('ngrok');
  return {
    ...options,
    headers: {
      'ngrok-skip-browser-warning': 'true',  // Bypass ngrok warning page
      ...options.headers,
    },
  };
}; 

const VisionPage = () => {
  const { speak, cancelSpeech, suspendListening, resumeListening } = useVoice();
  const { mode } = useMode();
  const { agility, cuesEnabled } = useSettings();
  
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentDescription, setCurrentDescription] = useState('Camera not active');
  const [detections, setDetections] = useState([]);
  const [annotatedImage, setAnnotatedImage] = useState(null);
  const [error, setError] = useState(null);
  const [lang, setLang] = useState('en');
  const [showCalibration, setShowCalibration] = useState(false);
  const [calibrationDistance, setCalibrationDistance] = useState('');
  const [isCalibrated, setIsCalibrated] = useState(false);
  const [calibK, setCalibK] = useState(null);
  const [qaMode, setQaMode] = useState(false);
  const [qaQuestion, setQaQuestion] = useState('');
  const [qaAnswer, setQaAnswer] = useState('');
  const [qaInProgress, setQaInProgress] = useState(false);
  
  // New state for camera selection: 'user' (front) or 'environment' (rear)
  const [facingMode, setFacingMode] = useState('user'); 
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false); // New state to check for multiple cameras

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const canvasRef = useRef(null);
  const latestTTS = useRef(null);
  const lastFrameRef = useRef(null);
  const speechMuteUntil = useRef(0); // suppress speech while answering questions
  const modeRef = useRef(mode);
  const agilityRef = useRef(agility);
  const cuesEnabledRef = useRef(cuesEnabled);
  const audioCtxRef = useRef(null);
  const lastCueRef = useRef({ sig: null, rank: 0, ts: 0 });
  const langRef = useRef(lang);
  const qaModeRef = useRef(qaMode);
  const qaInProgressRef = useRef(qaInProgress);
  const facingModeRef = useRef(facingMode);
  const analysisInFlightRef = useRef(false);
  const analysisRequestRef = useRef(0);
  const analysisLoopRef = useRef(0);
  const voiceSessionIdRef = useRef(
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `vision-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  const isSpeechMuted = () => Date.now() < speechMuteUntil.current;
  const muteSpeechFor = (ms) => { speechMuteUntil.current = Date.now() + ms; };

  // --- Non-speech cues (earcon + vibration) ---------------------------------
  // The AudioContext is created lazily inside a user gesture (Start / Switch
  // camera); browsers block or auto-suspend contexts created at load time.
  const ensureAudioContext = () => {
    try {
      if (!audioCtxRef.current) {
        const AudioCtor = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtor) return null;
        audioCtxRef.current = new AudioCtor();
      }
      if (audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume().catch(() => {});
      }
      return audioCtxRef.current;
    } catch (err) {
      console.warn('Could not initialise audio cues:', err);
      return null;
    }
  };

  const closeAudioContext = () => {
    const ctx = audioCtxRef.current;
    audioCtxRef.current = null;
    lastCueRef.current = { sig: null, rank: 0, ts: 0 };
    if (ctx && ctx.state !== 'closed') {
      ctx.close().catch(() => {});
    }
  };

  /**
   * Emit at most one cue per frame. Gated exactly like speech, and de-duplicated
   * because the loop re-sends the same alerts/urgency while a hazard persists.
   */
  const emitCue = (data) => {
    if (!cuesEnabledRef.current) return;
    if (qaInProgressRef.current || qaModeRef.current || isSpeechMuted()) return;

    const cue = selectCue(data);
    const prev = lastCueRef.current;

    if (!cue) {
      // Condition cleared: blank the signature so its return re-fires.
      lastCueRef.current = { ...prev, sig: null, rank: 0 };
      return;
    }

    const now = Date.now();
    if (!shouldFireCue(prev, cue, now)) return;

    lastCueRef.current = { sig: cueSignature(cue), rank: cue.rank, ts: now };
    playEarcon(audioCtxRef.current, cue);
    vibrateFor(cue.rank);
  };

  useEffect(() => {
    modeRef.current = mode;
    analysisRequestRef.current += 1;
    cancelSpeech();
  }, [mode]);

  useEffect(() => {
    langRef.current = lang;
  }, [lang]);

  useEffect(() => {
    agilityRef.current = agility;
  }, [agility]);

  useEffect(() => {
    cuesEnabledRef.current = cuesEnabled;
  }, [cuesEnabled]);

  useEffect(() => {
    qaModeRef.current = qaMode;
  }, [qaMode]);

  useEffect(() => {
    qaInProgressRef.current = qaInProgress;
  }, [qaInProgress]);

  useEffect(() => {
    facingModeRef.current = facingMode;
  }, [facingMode]);

  // Check calibration status, backend health, AND camera availability on mount
  useEffect(() => {
    const checkSetup = async () => {
      // 1. Check calibration and backend health
      try {
        const healthRes = await fetch(`${API_BASE_URL}/health`, getFetchOptions());
        if (!healthRes.ok) {
          console.warn('Backend server not responding');
          const isNgrok = API_BASE_URL.includes('ngrok');
          if (isNgrok) {
            toast.error('Cannot reach Colab backend. Make sure the server is running in Colab.');
          } else {
            toast.error('Cannot reach backend. Make sure it\'s running on localhost:5000 or set VITE_API_URL in .env');
          }
          return;
        }
        
        const res = await fetch(`${API_BASE_URL}/get_calib_K`, getFetchOptions());
        const data = await res.json();
        if (data.K) {
          setIsCalibrated(true);
          setCalibK(data.K);
        }
      } catch (err) {
        console.warn('Could not connect to backend:', err);
        toast.error('Cannot reach backend. Make sure it\'s running on localhost:5000');
      }

      // 2. Check for multiple cameras
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoDevices = devices.filter(device => device.kind === 'videoinput');
          if (videoDevices.length > 1) {
            setHasMultipleCameras(true);
          }
        } catch (err) {
          console.error('Error enumerating devices:', err);
          // Fails silently if no permission
        }
      }
    };
    checkSetup();

    // Initial check to see if we should use 'environment' by default on mobile (optional preference)
    // if (window.innerWidth <= 768) { 
    //   setFacingMode('environment');
    // }
  }, []);

  // Listen for voice commands (omitted for brevity, assume the cleanup/setup logic is in place)
  useEffect(() => {
    const handleVoiceStart = () => {
        if (!streamRef.current) {
            startCamera();
        }
    };

    const handleVoiceStop = () => stopCamera();
    const handleVoiceSwitch = () => toggleCamera();
    
    const handleVoiceCapture = () => {
        if (!streamRef.current) {
            startCamera();
        }
    };

    const handleVoiceCalibration = () => {
        setShowCalibration(true);
        speak("Calibration mode. Please enter the distance to the object in meters.");
    };

    const handleVoiceQA = () => {
        setQaMode(true);
        speak("Q&A mode activated. Please ask a question about the scene.");
    };

    window.addEventListener('voice-start-camera', handleVoiceStart);
    window.addEventListener('voice-stop-camera', handleVoiceStop);
    window.addEventListener('voice-switch-camera', handleVoiceSwitch);
    window.addEventListener('voice-capture', handleVoiceCapture);
    window.addEventListener('voice-start-calibration', handleVoiceCalibration);
    window.addEventListener('voice-start-qa', handleVoiceQA);

    // Handle inline scene questions (e.g. "where is my bottle") without navigating to chat
    const handleVoiceSceneQuestion = async (e) => {
      const question = e.detail?.question;
      if (!question) return;

      if (!streamRef.current) {
        speak("Camera is not active. Please say 'start camera' first.");
        return;
      }

      try {
        setQaInProgress(true);
        qaInProgressRef.current = true;
        suspendListening();
        cancelSpeech();
        analysisRequestRef.current += 1;
        analysisLoopRef.current += 1;
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
        muteSpeechFor(7000); // silence periodic descriptions while answering
        const blob = await captureFrame();
        if (!blob) { speak("Could not capture a frame to answer your question."); return; }

        const formData = new FormData();
        formData.append('frame', blob);
        formData.append('question', question);
        formData.append('session_id', voiceSessionIdRef.current);

        const response = await fetch(`${API_BASE_URL}/question`, getFetchOptions({ method: 'POST', body: formData }));
        const data = await response.json();
        if (response.ok && data.answer) {
          muteSpeechFor(Math.max(10000, data.answer.length * 75 + 4000));
          await speak(data.answer);
        } else {
          const answerError = data.error || "I couldn't find an answer to that.";
          muteSpeechFor(Math.max(8000, answerError.length * 75 + 3000));
          await speak(answerError);
        }
      } catch (err) {
        muteSpeechFor(8000);
        await speak("I had trouble analysing the scene. Please try again.");
        console.error('voice-scene-question error:', err);
      } finally {
        setQaInProgress(false);
        qaInProgressRef.current = false;
        resumeListening();
        startPeriodicAnalysis();
      }
    };
    window.addEventListener('voice-scene-question', handleVoiceSceneQuestion);

    // Cleanup
    return () => {
      if (streamRef.current) {
         // speak("Camera stopped."); // Removed because it clashes with stopCamera(true) below
         stopCamera(true); // Stop camera on unmount/re-effect
      } else {
         stopCamera(true);
      }
      window.removeEventListener('voice-start-camera', handleVoiceStart);
      window.removeEventListener('voice-stop-camera', handleVoiceStop);
      window.removeEventListener('voice-switch-camera', handleVoiceSwitch);
      window.removeEventListener('voice-capture', handleVoiceCapture);
      window.removeEventListener('voice-start-calibration', handleVoiceCalibration);
      window.removeEventListener('voice-start-qa', handleVoiceQA);
      window.removeEventListener('voice-scene-question', handleVoiceSceneQuestion);
    };
  }, []);

  const startCamera = async () => {
    if (streamRef.current) return; // Already running

    try {
      setError(null);
      const requestedFacingMode = facingModeRef.current;
      ensureAudioContext(); // user gesture — only safe place to open the audio context
      // Use the current facingMode in the constraints
      const constraints = {
        video: { 
          width: { ideal: 640 }, 
          height: { ideal: 480 },
          facingMode: requestedFacingMode
        },
        audio: false
      };

      speak(`Starting the ${requestedFacingMode === 'user' ? 'front' : 'rear'} camera. Ask me about anything in view.`);
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      
      streamRef.current = stream;
      if (videoRef.current) {
        // Set the video element to the new stream
        videoRef.current.srcObject = stream;
        // The following line is needed to apply the correct mirroring for 'user' (front) camera
        // In CSS, you'd apply transform: scaleX(-1) if facingMode is 'user'
      }

      try {
        await fetch(`${API_BASE_URL}/reset`, getFetchOptions({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: voiceSessionIdRef.current }),
        }));
      } catch (resetError) {
        console.warn('Could not reset backend temporal state:', resetError);
      }
      
      setIsStreaming(true);
      startPeriodicAnalysis(); // Starts the AI Loop immediately
    } catch (err) {
      console.error(err);
      setError(`Could not access camera (${requestedFacingMode}).`);
      toast.error("Camera access denied or device not available");
      speak("I cannot access the camera.");
    }
  };

  const stopCamera = (silent = false) => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (intervalRef.current) {
        clearTimeout(intervalRef.current);
        intervalRef.current = null;
    }
    analysisLoopRef.current += 1;
    if (videoRef.current) videoRef.current.srcObject = null;

    setIsStreaming(false);
    setIsAnalyzing(false);
    setCurrentDescription('Camera not active');
    setDetections([]);
    setAnnotatedImage(null);
    latestTTS.current = null;
    analysisRequestRef.current += 1;
    cancelSpeech();
    closeAudioContext();

    if (!silent) speak("Camera stopped.");
  };

  // New function to switch cameras
  const toggleCamera = () => {
    const currentFacingMode = facingModeRef.current;
    const newFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
    facingModeRef.current = newFacingMode;
    setFacingMode(newFacingMode);

    if (streamRef.current) {
      // 1. Stop the current stream silently
      stopCamera(true); 
      restartCameraWithMode(newFacingMode);
    } else {
      speak(`${newFacingMode === 'user' ? 'Front' : 'Rear'} camera selected.`);
    }
  };

  // Helper to restart camera immediately after toggle
  const restartCameraWithMode = async (mode) => {
      try {
          setError(null);
          ensureAudioContext(); // stopCamera() closed it; the toggle is a user gesture
          const constraints = {
              video: { 
                  width: { ideal: 640 }, 
                  height: { ideal: 480 },
                  facingMode: mode 
              },
              audio: false
          };
          
          speak(`Switching to ${mode === 'user' ? 'front' : 'rear'} camera.`);
          
          const stream = await navigator.mediaDevices.getUserMedia(constraints);
          
          streamRef.current = stream;
          if (videoRef.current) {
              videoRef.current.srcObject = stream;
          }

          try {
              await fetch(`${API_BASE_URL}/reset`, getFetchOptions({
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: voiceSessionIdRef.current }),
              }));
          } catch (resetError) {
              console.warn('Could not reset backend temporal state:', resetError);
          }
          
          setIsStreaming(true);
          startPeriodicAnalysis();
      } catch (err) {
          console.error(err);
          setError(`Could not access camera (${mode}).`);
          toast.error("Camera switch failed. Device may not support this camera.");
          speak("I cannot switch the camera.");
          setIsStreaming(false);
      }
  }


  const captureFrame = () => {
    if (!videoRef.current || !canvasRef.current) return null;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    canvas.width = 480; 
    canvas.height = 360;
    
    // Apply horizontal flip for 'user' facing mode during capture to match user expectation (optional)
    if (facingModeRef.current === 'user') {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }

    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    
    // Reset canvas transformation
    if (facingModeRef.current === 'user') {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.7));
  };

  const analyzeFrame = async () => {
    if (analysisInFlightRef.current) return;
    if (qaInProgressRef.current) return;

    const requestId = analysisRequestRef.current + 1;
    analysisRequestRef.current = requestId;
    const requestMode = modeRef.current;

    try {
      analysisInFlightRef.current = true;
      setIsAnalyzing(true);
      const blob = await captureFrame();
      if (!blob) return;

      const formData = new FormData();
      formData.append('frame', blob, 'frame.jpg');
      formData.append('lang', langRef.current);
      formData.append('mode', requestMode);
      formData.append('agility', agilityRef.current);
      formData.append('session_id', voiceSessionIdRef.current);

      const response = await fetch(`${API_BASE_URL}/analyze_frame`, getFetchOptions({
        method: 'POST',
        body: formData,
      }));

      if (!response.ok) throw new Error("Network error");
      
      const data = await response.json();
      if (
        requestId !== analysisRequestRef.current
        || requestMode !== modeRef.current
        || data.mode !== requestMode
      ) {
        return;
      }

      if (data) {
        setDetections(data.detections || []);

        // Determine caption: prefer backend caption but replace BLIP-2 "not loaded" messages
        let caption = data.caption || '';
        const blipUnavailablePatterns = ['BLIP-2', 'not loaded', 'Scene analysis unavailable', 'BLIP-2 not loaded'];
        const isBlipUnavailable = blipUnavailablePatterns.some(p => caption && caption.includes(p));

        if (isBlipUnavailable) {
          // Create a simple detection-based caption as fallback
          if (data.detections && data.detections.length > 0) {
            const names = Array.from(new Set(data.detections.map(d => d.class)));
            caption = `Scene contains: ${names.join(', ')}`;
          } else {
            caption = 'No obvious objects detected';
          }
        }

        if (caption) {
          setCurrentDescription(caption);
        }

        // Non-speech cues run alongside speech, and lead it slightly: the earcon
        // localises the hazard while the sentence explains it. Scheduling is
        // non-blocking, so this does not delay speak() below.
        emitCue(data);

        if (
          data.speech
          && !qaInProgressRef.current
          && !qaModeRef.current
          && !isSpeechMuted()
        ) {
          speak(data.speech);
        }

        // Handle wall alerts with 3-second cooldown (handled by backend)
        if (data.wall_alert && !qaInProgress && !qaMode && !isSpeechMuted()) {
          const wallMsg = data.wall_alert.message;
          if (data.wall_alert.urgent) {
            // Urgent wall alert - speak immediately and show toast
            toast.error(wallMsg, { duration: 5000 });
          } else {
            // Regular wall alert
            toast(wallMsg, { icon: '⚠️', duration: 3000 });
          }
        }

        // Update annotated image
        if (data.annotated_image) {
          setAnnotatedImage(`data:image/png;base64,${data.annotated_image}`);
        }
      }
    } catch (err) {
      console.error(err);
      setError('Analysis failed: ' + err.message);
    } finally {
      analysisInFlightRef.current = false;
      setIsAnalyzing(false);
    }
  };

  const startPeriodicAnalysis = () => {
    const loopId = analysisLoopRef.current + 1;
    analysisLoopRef.current = loopId;

    if (intervalRef.current) {
      clearTimeout(intervalRef.current);
      intervalRef.current = null;
    }

    const runAndSchedule = async () => {
      if (loopId !== analysisLoopRef.current || !streamRef.current) return;
      await analyzeFrame();
      if (loopId === analysisLoopRef.current && streamRef.current) {
        intervalRef.current = setTimeout(runAndSchedule, 2500);
      }
    };

    runAndSchedule();
  };

  const handleCalibrate = async () => {
    if (!calibrationDistance || isNaN(parseFloat(calibrationDistance))) {
      setError('Please enter a valid distance in meters');
      return;
    }

    try {
      const blob = await captureFrame();
      if (!blob) {
        setError('Could not capture frame for calibration');
        return;
      }

      const formData = new FormData();
      formData.append('frame', blob);
      formData.append('distance_m', parseFloat(calibrationDistance));

      const response = await fetch(`${API_BASE_URL}/calibrate`, getFetchOptions({
        method: 'POST',
        body: formData,
      }));

      const data = await response.json();
      if (response.ok) {
        setIsCalibrated(true);
        setCalibK(data.K);
        setShowCalibration(false);
        setCalibrationDistance('');
        speak(`Calibration successful. Distance factor set to ${data.K.toFixed(3)}`);
        toast.success('Calibration successful!');
      } else {
        setError(data.error || 'Calibration failed');
        speak('Calibration failed. Please try again.');
      }
    } catch (err) {
      setError('Calibration error: ' + err.message);
      console.error(err);
    }
  };

  const handleQA = async () => {
    if (!qaQuestion.trim()) {
      setError('Please ask a question');
      return;
    }

    // Pause periodic analysis and mark QA in progress
    setQaInProgress(true);
    qaInProgressRef.current = true;
    analysisLoopRef.current += 1;
    muteSpeechFor(6000); // keep quiet during and shortly after the answer
    toast.dismiss();
    if (intervalRef.current) {
      clearTimeout(intervalRef.current);
      intervalRef.current = null;
    }

    try {
      setQaAnswer('');
      const blob = await captureFrame();
      if (!blob) {
        setError('Could not capture frame for Q&A');
        return;
      }

      const formData = new FormData();
      formData.append('frame', blob);
      formData.append('question', qaQuestion);
      formData.append('session_id', voiceSessionIdRef.current);

      const response = await fetch(`${API_BASE_URL}/question`, getFetchOptions({
        method: 'POST',
        body: formData,
      }));

      const data = await response.json();
      if (response.ok) {
        setQaAnswer(data.answer);
        speak(`${data.answer}`);
        // No toast - just show the answer on screen and speak it
      } else {
        const errorMsg = data.error || 'Q&A failed';
        setError(errorMsg);
        speak(errorMsg);
      }
    } catch (err) {
      setError('Q&A error: ' + err.message);
      console.error(err);
    } finally {
      // Resume periodic analysis
      setQaInProgress(false);
      qaInProgressRef.current = false;
      startPeriodicAnalysis();
    }
  };

  const playAudio = () => {
    if (latestTTS.current) {
      new Audio(`data:audio/mp3;base64,${latestTTS.current}`).play();
    } else {
      speak(currentDescription); 
    }
  };

  // Determine if we should apply the mirror effect via CSS class
  const videoClass = `webcam-video ${facingMode === 'user' ? 'mirrored' : ''}`;


  return (
    <div className="webcam-component">
      <div className="webcam-header">
        <h2>Real-time Vision Analysis 3.0</h2>
        <p>YOLOv8 + ByteTrack + Depth Anything + Florence-2</p>
        {!isCalibrated && (
          <div className="calibration-warning">
            <AlertCircle size={18} />
            <span>Distance calibration recommended for accurate distance estimation</span>
          </div>
        )}
        {isCalibrated && (
          <div className="calibration-success">
            <CheckCircle size={18} />
            <span>Calibrated (K = {calibK?.toFixed(3)})</span>
          </div>
        )}
      </div>

      <div className="webcam-content">
        <div className="video-section">
          <div className="video-container">
            {/* Apply the mirrored class based on facingMode state */}
            <video ref={videoRef} autoPlay playsInline muted className={videoClass} /> 
            <canvas ref={canvasRef} style={{ display: 'none' }} />
            {!isStreaming && (
              <div className="video-placeholder">
                <Camera className="placeholder-icon" size={48} />
                <p>Camera not active</p>
              </div>
            )}
          </div>

          <div className="video-controls">
            <div className="control-block">
              {!isStreaming ? (
                <motion.button 
                  whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                  onClick={startCamera} 
                  className="control-button start-button"
                >
                  <Play size={20} /> Start Camera
                </motion.button>
              ) : (
                <motion.button 
                  whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                  onClick={() => stopCamera(false)} 
                  className="control-button stop-button"
                >
                  <Square size={20} /> Stop Camera
                </motion.button>
              )}
            </div>
            
            {/* New Switch Camera Button */}
            {hasMultipleCameras && (
                <motion.button 
                    whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                    onClick={toggleCamera} 
                    className="control-button switch-button"
                    title={`Switch to ${facingMode === 'user' ? 'Rear' : 'Front'} Camera`}
                >
                    <RefreshCw size={20} /> 
                    {facingMode === 'user' ? 'Switch to Rear' : 'Switch to Front'}
                </motion.button>
            )}
            
            <motion.button 
              whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
              onClick={() => setQaMode(!qaMode)} 
              disabled={!isStreaming}
              className="control-button qa-button"
              title="Toggle Ask AI panel"
            >
              <Mic size={20} /> {qaMode ? 'Close' : 'Ask AI'}
            </motion.button>
          </div>

          <div className="control-buttons-row">
            <motion.button 
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              onClick={() => setShowCalibration(!showCalibration)}
              className="secondary-button calibrate-button"
              disabled={!isStreaming}
            >
              <Zap size={18} /> {isCalibrated ? 'Recalibrate' : 'Calibrate'}
            </motion.button>
          </div>

          <div className="voice-select-wrapper control-block-select">
            <select value={lang} onChange={(e) => setLang(e.target.value)} className="voice-select">
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="mr">Marathi</option>
            </select>
          </div>

          {/* Calibration Panel */}
          {showCalibration && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="calibration-panel"
            >
              <h4>Distance Calibration</h4>
              <p>Enter the real-world distance to the object in your camera view (in meters)</p>
              <input
                type="number"
                placeholder="Distance (e.g., 2.5)"
                value={calibrationDistance}
                onChange={(e) => setCalibrationDistance(e.target.value)}
                step="0.1"
                min="0.1"
                className="calibration-input"
              />
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleCalibrate}
                className="calibration-submit-button"
              >
                Calibrate
              </motion.button>
            </motion.div>
          )}

          {/* Q&A Panel - Always Visible */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: qaMode ? 1 : 0, y: qaMode ? 0 : 10 }}
            transition={{ duration: 0.2 }}
            className="qa-panel"
            style={{ pointerEvents: qaMode ? 'auto' : 'none' }}
          >
            <div className="qa-panel-header">
              <h4>Ask AI About the Scene</h4>
              <button 
                onClick={() => setQaMode(false)} 
                className="qa-close-button"
                title="Close Q&A panel"
              >
                <X size={20} />
              </button>
            </div>
            <input
              type="text"
              placeholder="Ask a question..."
              value={qaQuestion}
              onChange={(e) => setQaQuestion(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleQA()}
              className="qa-input"
              autoFocus={qaMode}
            />
            <button onClick={handleQA} className="qa-submit-button">
              Get Answer
            </button>
            {qaAnswer && (
              <div className="qa-answer">
                <strong>Answer:</strong> {qaAnswer}
              </div>
            )}
          </motion.div>
        </div>

        <div className="analysis-section">
          {annotatedImage && (
            <div className="annotated-image-container">
              <img src={annotatedImage} alt="AI Vision" className="annotated-image" />
            </div>
          )}
          
          {detections.length > 0 && (
            <div className="detections-card">
              <h4>Detected Objects ({detections.length})</h4>
              <div className="detections-list">
                {detections.map((det, idx) => (
                  <div key={idx} className="detection-item">
                    <CheckCircle className="detection-icon" size={16} />
                    <span className="detection-class">{det.class}</span>
                    <span className="detection-side">{det.side}</span>
                    <span className="detection-distance">{det.distance_str}</span>
                    <span className="detection-confidence">{(det.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <div className="description-card">
            <h4>Scene Description</h4>
            <p className="description-text">{currentDescription}</p>
          </div>
          
          {error && (
            <div className="error-card">
              <AlertCircle size={20} />
              <p>{error}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VisionPage;
